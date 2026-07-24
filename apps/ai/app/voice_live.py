"""WebSocket de voz en tiempo real (/ws/voice/live) — Deepgram STT/TTS +
el MISMO agente RAG que ya usa el chat SSE (assistant.py). Deepgram solo
transcribe y genera audio; el turno lo resuelve `_run_llm`/`_run_demo` sin
tocarlos — mismo RAG, mismas tools, misma memoria que el chat web.

Solo lo consume el gateway WS de NestJS (nunca el navegador directo, ver
design.md) — Nest relaya audio binario + frames JSON en ambas direcciones
sin transformarlos. Este módulo NO escribe en Postgres (AiCall/CallMessage):
esa persistencia la hace Nest espiando `transcript_final`/`turn_end`.

Protocolo completo: openspec/changes/live-call-deepgram/design.md
Verificado contra developers.deepgram.com (jul 2026):
  - STT wss://api.deepgram.com/v1/listen — Authorization: Token <key>,
    audio binario crudo, respuestas JSON {"type":"Results", is_final,
    channel.alternatives[0].transcript}.
  - TTS wss://api.deepgram.com/v1/speak — Authorization: Token <key>,
    {"type":"Speak","text":...} encola texto, {"type":"Flush"} pide el
    audio ya, {"type":"Clear"} descarta todo (usado en el barge-in).
"""
import asyncio
import json
import logging
import re
import uuid
from typing import AsyncIterator, Optional

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from . import auth, config, memory
from .assistant import _remember, _run_demo, _run_llm

log = logging.getLogger("seguria.voice_live")
router = APIRouter()

_AUTH_TIMEOUT_S = 10

DEEPGRAM_LISTEN_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?encoding=linear16&sample_rate=16000&channels=1"
    "&interim_results=true&endpointing=300"
)


def _deepgram_speak_url() -> str:
    return (
        "wss://api.deepgram.com/v1/speak"
        f"?model={config.DEEPGRAM_VOICE_MODEL}&encoding=linear16&sample_rate=24000"
    )


def _parse_sse_frame(frame: str) -> Optional[tuple[str, dict]]:
    """Parsea 'event: X\\ndata: {json}\\n\\n' (formato de `_frame` en
    assistant.py) de vuelta a (event, data). Así se reusan `_run_llm`/
    `_run_demo` literalmente sin tocarlos ni duplicar su lógica."""
    lines = frame.strip("\n").split("\n")
    if len(lines) != 2 or not lines[0].startswith("event: ") or not lines[1].startswith("data: "):
        return None
    event = lines[0][len("event: "):]
    try:
        data = json.loads(lines[1][len("data: "):])
    except json.JSONDecodeError:
        return None
    return event, data


class DeepgramSTT:
    """Conexión saliente a Deepgram `/v1/listen`. Reenvía el audio del
    navegador (ya relayado por Nest) y expone los transcripts parciales y
    finales tal como los devuelve Deepgram."""

    def __init__(self) -> None:
        self._ws = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            DEEPGRAM_LISTEN_URL,
            additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
        )

    async def send_audio(self, chunk: bytes) -> None:
        if self._ws is not None:
            await self._ws.send(chunk)

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "CloseStream"}))
        except ConnectionClosed:
            pass
        await self._ws.close()
        self._ws = None

    async def transcripts(self) -> AsyncIterator[tuple[bool, str]]:
        """Yields (is_final, transcript) por cada resultado con texto."""
        assert self._ws is not None
        try:
            async for raw in self._ws:
                if isinstance(raw, (bytes, bytearray)):
                    continue  # Deepgram no manda binario en /v1/listen
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "Results":
                    continue
                alternatives = msg.get("channel", {}).get("alternatives", [])
                transcript = (alternatives[0].get("transcript") if alternatives else "") or ""
                if not transcript.strip():
                    continue
                yield bool(msg.get("is_final")), transcript
        except ConnectionClosed:
            return


class DeepgramTTS:
    """Conexión saliente a Deepgram `/v1/speak`. Se abre una por turno: habla
    el texto completo del turno, pide `Flush`, reenvía el audio y se cierra.
    `cancel()` (barge-in) manda `Clear` y corta la conexión de inmediato."""

    def __init__(self) -> None:
        self._ws = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            _deepgram_speak_url(),
            additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
        )

    async def speak(self, text: str) -> None:
        if self._ws is not None and text:
            await self._ws.send(json.dumps({"type": "Speak", "text": text}))

    async def flush(self) -> None:
        if self._ws is not None:
            await self._ws.send(json.dumps({"type": "Flush"}))

    async def cancel(self) -> None:
        """Barge-in: descarta el texto/audio en cola y cierra ya mismo."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "Clear"}))
        except ConnectionClosed:
            pass
        await self._ws.close()
        self._ws = None

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "Close"}))
        except ConnectionClosed:
            pass
        await self._ws.close()
        self._ws = None

    async def audio_chunks(self) -> AsyncIterator[bytes]:
        """Yields bytes de audio; ignora los mensajes JSON de control
        (Metadata/Flushed/Cleared/Warning) — son telemetría, no playback."""
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                if isinstance(raw, (bytes, bytearray)):
                    yield raw
        except ConnectionClosed:
            return


class VoiceSession:
    """Estado por conexión: auth -> abre Deepgram STT -> loop de turnos ->
    limpieza. Un turno = transcript final -> agente RAG -> Deepgram TTS."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.session_id = str(uuid.uuid4())
        self.user_id = ""
        self.tenant_id = ""
        self.role = "cliente"
        self.muted = False
        self.assistant_speaking = False
        self.turns_completed = 0
        self.stt = DeepgramSTT()
        self._tts: Optional[DeepgramTTS] = None
        self._turn_task: Optional[asyncio.Task] = None

    async def _send_json(self, type_: str, data: dict) -> None:
        await self.ws.send_json({"type": type_, "data": data})

    async def authenticate(self) -> bool:
        """Primer frame esperado: `{"type":"auth","data":{"token":...}}`."""
        try:
            raw = await asyncio.wait_for(self.ws.receive_json(), timeout=_AUTH_TIMEOUT_S)
            if raw.get("type") != "auth":
                raise ValueError("se esperaba el frame 'auth' primero")
            token = (raw.get("data") or {}).get("token", "")
            claims = auth.decode_token(token)
            if not claims:
                raise ValueError("token inválido o expirado")
        except Exception as exc:
            try:
                await self._send_json("auth_error", {"reason": str(exc)})
            except Exception:
                pass
            return False

        self.user_id = f"web:{claims['sub']}"
        self.tenant_id = claims.get("teamId") or config.DEMO_TENANT_ID
        self.role = "gerente" if claims.get("role") in {"GERENTE", "ADMIN"} else "cliente"
        await self._send_json("auth_ok", {})
        return True

    async def run(self) -> None:
        await self.ws.accept()
        if not config.DEEPGRAM_API_KEY:
            await self._send_json("auth_error", {"reason": "Deepgram no configurado"})
            await self.ws.close(code=1011)
            return
        if not await self.authenticate():
            await self.ws.close(code=4401)
            return

        try:
            await self.stt.connect()
        except Exception as exc:
            log.warning("no se pudo conectar a Deepgram STT: %s", exc)
            await self._send_json("error", {"message": "Deepgram STT no disponible"})
            await self.ws.close(code=1011)
            return

        stt_task = asyncio.create_task(self._stt_loop())
        client_task = asyncio.create_task(self._client_loop())
        _done, pending = await asyncio.wait(
            {stt_task, client_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        await self._cleanup()

    async def _client_loop(self) -> None:
        """Lee frames del navegador (vía Nest): binario = audio, JSON = control."""
        try:
            while True:
                message = await self.ws.receive()
                if message["type"] == "websocket.disconnect":
                    return
                data = message.get("bytes")
                if data is not None:
                    if not self.muted:
                        await self.stt.send_audio(data)
                    continue
                text = message.get("text")
                if text is None:
                    continue
                control = json.loads(text)
                ctype = control.get("type")
                if ctype == "mute":
                    self.muted = True
                elif ctype == "unmute":
                    self.muted = False
                elif ctype == "end_call":
                    return
        except WebSocketDisconnect:
            return

    async def _stt_loop(self) -> None:
        async for is_final, transcript in self.stt.transcripts():
            if not is_final:
                await self._send_json("transcript_partial", {"text": transcript})
                continue
            await self._send_json("transcript_final", {"text": transcript})
            if self.assistant_speaking:
                await self._barge_in()
            if self._turn_task and not self._turn_task.done():
                self._turn_task.cancel()
            self._turn_task = asyncio.create_task(self._run_turn(transcript))

    async def _barge_in(self) -> None:
        """El usuario habló mientras la IA hablaba: corta TTS en curso."""
        self.assistant_speaking = False  # corta el loop de audio en _speak
        if self._tts is not None:
            await self._tts.cancel()
            self._tts = None
        await self._send_json("barge_in", {})

    async def _run_turn(self, transcript: str) -> None:
        out: dict = {"reply": ""}
        try:
            await self._send_json("thinking", {"text": "Analizando tu mensaje..."})
            mem_ctx = await memory.get_memory_context(self.user_id, tenant_id=self.tenant_id)
            runner = _run_llm if config.DEEPSEEK_API_KEY else _run_demo
            async for frame in runner(self.session_id, transcript, mem_ctx, self.role,
                                       self.user_id, self.tenant_id, out):
                parsed = _parse_sse_frame(frame)
                if parsed is None:
                    continue
                event, data = parsed
                if event == "done":
                    continue
                await self._send_json(event, data)
            await _remember(self.user_id, transcript, self.tenant_id)
        except Exception as exc:
            log.exception("fallo en el turno de voz")
            await self._send_json("error", {"message": f"Ocurrió un problema técnico: {exc}"})

        reply_text = out.get("reply", "")
        await self._send_json("turn_end", {"reply_text": reply_text})
        self.turns_completed += 1
        if reply_text.strip():
            await self._speak(reply_text)

    async def _speak(self, text: str) -> None:
        """Sintetiza `text` completo por Deepgram TTS y reenvía el audio."""
        self._tts = DeepgramTTS()
        try:
            await self._tts.connect()
        except Exception as exc:
            log.warning("no se pudo conectar a Deepgram TTS: %s", exc)
            await self._send_json("error", {"message": "Deepgram TTS no disponible"})
            self._tts = None
            return

        await self._send_json("assistant_speaking_start", {})
        self.assistant_speaking = True
        await self._tts.speak(text)
        await self._tts.flush()
        async for chunk in self._tts.audio_chunks():
            if not self.assistant_speaking:
                break  # un barge-in canceló mientras se reproducía
            await self.ws.send_bytes(chunk)
        await self._tts.close()
        self._tts = None
        if self.assistant_speaking:
            self.assistant_speaking = False
            await self._send_json("assistant_speaking_end", {})

    async def _cleanup(self) -> None:
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        await self.stt.close()
        if self._tts is not None:
            await self._tts.close()
        try:
            await self.ws.close()
        except RuntimeError:
            pass  # ya estaba cerrado


@router.websocket("/ws/voice/live")
async def voice_live(ws: WebSocket) -> None:
    await VoiceSession(ws).run()
