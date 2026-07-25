"""WebSocket de voz en tiempo real (/ws/voice/live) — Deepgram STT/TTS +
el MISMO agente RAG que ya usa el chat SSE (assistant.py). Deepgram solo
transcribe y genera audio; el turno lo resuelve `_run_llm`/`_run_demo` sin
tocarlos — mismo RAG, mismas tools, misma memoria que el chat web.

Solo lo consume el gateway WS de NestJS (nunca el navegador directo, ver
design.md) — Nest relaya audio binario + frames JSON en ambas direcciones
sin transformarlos. Este módulo NO escribe en Postgres (AiCall/CallMessage):
esa persistencia la hace Nest espiando `transcript_final`/`turn_end`.

Protocolo completo: openspec/changes/live-call-deepgram/design.md,
openspec/changes/live-call-voice-quality/design.md
Verificado contra developers.deepgram.com (jul 2026):
  - STT `nova-*` wss://api.deepgram.com/v1/listen — Authorization: Token
    <key>, audio binario crudo, respuestas JSON {"type":"Results",
    is_final, channel.alternatives[0].transcript}.
  - STT `flux-*` wss://api.deepgram.com/v2/listen — mismo audio binario,
    respuestas {"type":"TurnInfo", "event": ..., "transcript": ...} (turno
    semántico, no de silencio; ver DeepgramSTT.transcripts()).
  - TTS wss://api.deepgram.com/v1/speak — Authorization: Token <key>,
    {"type":"Speak","text":...} encola texto, {"type":"Flush"} pide el
    audio ya (conexión PERSISTENTE para toda la llamada, no por turno),
    {"type":"Clear"} descarta todo sin cerrar (usado en el barge-in).
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


def _deepgram_listen_url() -> str:
    """STT en español (LATAM). Con un modelo `flux-*` usa el endpoint nuevo
    `/v2/listen` (detección de turno SEMÁNTICA, no de silencio — ver
    `DeepgramSTT.transcripts()`); con cualquier otro modelo (`nova-3` por
    defecto) sigue en `/v1/listen`, donde el turno cierra con `speech_final`
    tras `endpointing` ms de silencio. Cambiar de uno a otro es solo
    `DEEPGRAM_STT_MODEL` (rollback sin tocar código)."""
    if config.DEEPGRAM_STT_MODEL.startswith("flux-"):
        return (
            "wss://api.deepgram.com/v2/listen"
            f"?model={config.DEEPGRAM_STT_MODEL}"
            f"&language_hint={config.DEEPGRAM_LANGUAGE}"
            "&encoding=linear16&sample_rate=16000"
        )
    endpointing = max(10, config.DEEPGRAM_ENDPOINTING_MS)
    return (
        "wss://api.deepgram.com/v1/listen"
        f"?model={config.DEEPGRAM_STT_MODEL}"
        f"&language={config.DEEPGRAM_LANGUAGE}"
        "&encoding=linear16&sample_rate=16000&channels=1"
        f"&interim_results=true&endpointing={endpointing}"
    )


def _deepgram_speak_url() -> str:
    return (
        "wss://api.deepgram.com/v1/speak"
        f"?model={config.DEEPGRAM_VOICE_MODEL}&encoding=linear16&sample_rate=24000"
    )


def _normalize_echo_text(text: str) -> str:
    """Minúsculas + sin puntuación, para comparar eco TTS→mic."""
    lowered = text.strip().lower()
    return re.sub(r"[^\w\s]", "", lowered, flags=re.UNICODE)


def looks_like_echo(transcript: str, last_spoken: str, *, min_chars: int = 8) -> bool:
    """True si el transcript final parece eco del último TTS (parlante→mic)."""
    t = _normalize_echo_text(transcript)
    last = _normalize_echo_text(last_spoken)
    if len(t) < min_chars or len(last) < min_chars:
        return False
    if t in last or last in t:
        return True
    t_words = set(t.split())
    last_words = set(last.split())
    if not t_words:
        return False
    overlap = len(t_words & last_words) / len(t_words)
    return overlap >= 0.8 and len(t_words) <= len(last_words) + 2


_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


class _SentenceSplitter:
    """Acumula texto de `token` y libera oraciones completas a medida que
    llegan — así se puede hablar la primera oración sin esperar a que el
    LLM termine la respuesta entera."""

    def __init__(self) -> None:
        self.buf = ""

    def push(self, delta: str) -> list[str]:
        self.buf += delta
        parts = _SENTENCE_END_RE.split(self.buf)
        if len(parts) <= 1:
            return []
        *complete, self.buf = parts
        return [p.strip() for p in complete if p.strip()]

    def finish(self) -> str:
        rest = self.buf.strip()
        self.buf = ""
        return rest


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
            _deepgram_listen_url(),
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

    async def transcripts(self) -> AsyncIterator[tuple[str, str]]:
        """Yields (`partial`|`utterance`, text).

        - `partial`: interim o segmento `is_final` a mitad de frase (solo UI / barge-in).
        - `utterance`: el usuario dejó de hablar; ahí arranca el turno.

        Dos esquemas de mensaje según `DEEPGRAM_STT_MODEL` (ver `_deepgram_listen_url`):
        - `nova-*` (`/v1/listen`): `speech_final` tras `endpointing` ms de
          silencio cierra el turno. Arrancar el agente en cada `is_final`
          cancelaba el LLM a mitad de frase y se sentía trabado.
        - `flux-*` (`/v2/listen`): un solo tipo `TurnInfo` con un campo
          `event` (`Update`/`StartOfTurn`/`EagerEndOfTurn`/`TurnResumed`/
          `EndOfTurn`) y el transcript del turno en curso en `transcript`
          (raíz del mensaje, NO bajo `channel.alternatives` — verificado
          contra developers.deepgram.com/reference/speech-to-text/listen-flux,
          jul 2026). `EndOfTurn` es el cierre semántico (<400ms, no
          silencio); `EagerEndOfTurn` es un adelanto que `TurnResumed` puede
          desmentir si el usuario sigue hablando — ambos se tratan como
          `partial` acá, nunca disparan el turno por sí solos.
        """
        assert self._ws is not None
        is_flux = config.DEEPGRAM_STT_MODEL.startswith("flux-")
        pending: list[str] = []
        try:
            async for raw in self._ws:
                if isinstance(raw, (bytes, bytearray)):
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if is_flux:
                    if msg.get("type") != "TurnInfo":
                        continue
                    transcript = (msg.get("transcript") or "").strip()
                    event = msg.get("event")
                    if event == "EndOfTurn":
                        if transcript:
                            yield "utterance", transcript
                    elif event in ("Update", "EagerEndOfTurn") and transcript:
                        yield "partial", transcript
                    continue

                if msg.get("type") != "Results":
                    continue
                alternatives = msg.get("channel", {}).get("alternatives", [])
                transcript = (alternatives[0].get("transcript") if alternatives else "") or ""
                is_final = bool(msg.get("is_final"))
                speech_final = bool(msg.get("speech_final"))

                if not is_final:
                    shown = (" ".join(pending + [transcript.strip()])).strip()
                    if shown:
                        yield "partial", shown
                    continue

                if transcript.strip():
                    pending.append(transcript.strip())
                    # Progreso de la frase ya confirmada (aún sin silencio final).
                    if not speech_final:
                        yield "partial", " ".join(pending)

                if speech_final:
                    full = " ".join(pending).strip()
                    pending.clear()
                    if full:
                        yield "utterance", full
        except ConnectionClosed:
            return


class DeepgramTTS:
    """Conexión saliente a Deepgram `/v1/speak` — PERSISTENTE para toda la
    llamada (se conecta una vez en `VoiceSession.run()`, no por turno).
    `cancel()` (barge-in) manda `Clear` SIN cerrar la conexión; solo
    `close()` la cierra de verdad, al terminar la llamada."""

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
        """Barge-in: descarta el texto/audio en cola. NO cierra el socket —
        la conexión sigue viva para el resto de la llamada."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "Clear"}))
        except ConnectionClosed:
            pass

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "Close"}))
        except ConnectionClosed:
            pass
        await self._ws.close()
        self._ws = None

    async def messages(self) -> AsyncIterator[tuple[str, Optional[bytes]]]:
        """Yields `("audio", bytes)` por cada chunk, o `("flushed", None)`
        cuando Deepgram confirma que ya renderizó todo lo pedido en el
        último `Flush` — así el llamador sabe cuándo cortar el drenaje de
        UNA oración sin tener que cerrar la conexión (persistente)."""
        if self._ws is None:
            return
        try:
            async for raw in self._ws:
                if isinstance(raw, (bytes, bytearray)):
                    yield "audio", raw
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "Flushed":
                    yield "flushed", None
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
        self._tts = DeepgramTTS()
        self._turn_task: Optional[asyncio.Task] = None
        # Tokens de generación: barge-in / cancel invalidan turnos y TTS en vuelo.
        self._turn_gen = 0
        self._speak_gen = 0
        self._last_spoken_text = ""

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
            # TTS persistente: una sola conexión para TODA la llamada — antes
            # se abría una por turno, sumando un handshake completo a cada
            # respuesta hablada.
            await self._tts.connect()
        except Exception as exc:
            log.warning("no se pudo conectar a Deepgram STT/TTS: %s", exc)
            await self._send_json("error", {"message": "Deepgram no disponible"})
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
        async for event, transcript in self.stt.transcripts():
            if event == "partial":
                await self._send_json("transcript_partial", {"text": transcript})
                # Interim / segmento parcial: solo corta TTS si la IA habla.
                if self.assistant_speaking and transcript.strip():
                    await self._barge_in()
                continue

            # event == "utterance" (speech_final): el usuario terminó de hablar.
            await self._send_json("transcript_final", {"text": transcript})
            if self.assistant_speaking:
                await self._barge_in()

            if looks_like_echo(transcript, self._last_spoken_text):
                log.info("descartando transcript eco del TTS: %r", transcript[:120])
                continue

            self._turn_gen += 1
            if self._turn_task and not self._turn_task.done():
                self._turn_task.cancel()
            self._turn_task = asyncio.create_task(self._run_turn(transcript))

    async def _barge_in(self) -> None:
        """Corta TTS en curso: `Clear` en la MISMA conexión persistente (ya
        no se cierra/reabre) e invalida `_speak_gen` para que el drenaje de
        audio en vuelo de `_speak_sentence` corte de inmediato."""
        self.assistant_speaking = False
        self._speak_gen += 1
        await self._tts.cancel()
        await self._send_json("barge_in", {})

    async def _run_turn(self, transcript: str) -> None:
        gen = self._turn_gen
        out: dict = {"reply": ""}
        splitter = _SentenceSplitter()
        try:
            await self._send_json("thinking", {"text": "Analizando tu mensaje..."})
            mem_ctx = await memory.get_memory_context(self.user_id, tenant_id=self.tenant_id)
            runner = _run_llm if config.DEEPSEEK_API_KEY else _run_demo
            # `channel="voice"` selecciona el prompt de cierre (Camilo) en vez
            # de Sofía — ya trae las restricciones de voz (respuestas cortas,
            # no leer URLs, no re-saludar si el historial ya tiene turnos
            # previos), así que el transcript va SIN prefijo/hint: eso antes
            # ensuciaba `chat_history` con texto de instrucción disfrazado de
            # habla del cliente (ver `_history_user_message`).
            async for frame in runner(
                self.session_id, transcript, mem_ctx, self.role,
                self.user_id, self.tenant_id, out, channel="voice",
            ):
                if gen != self._turn_gen:
                    return
                parsed = _parse_sse_frame(frame)
                if parsed is None:
                    continue
                event, data = parsed
                if event == "done":
                    continue
                await self._send_json(event, data)
                if event == "token":
                    for sentence in splitter.push(data.get("text", "")):
                        if gen != self._turn_gen:
                            return
                        await self._speak_sentence(gen, sentence)
            if gen != self._turn_gen:
                return
            await _remember(self.user_id, transcript, self.tenant_id)
        except asyncio.CancelledError:
            await self._end_speaking()
            return
        except Exception as exc:
            await self._end_speaking()
            if gen != self._turn_gen:
                return
            log.exception("fallo en el turno de voz")
            await self._send_json("error", {"message": f"Ocurrió un problema técnico: {exc}"})
            return

        if gen != self._turn_gen:
            await self._end_speaking()
            return

        reply_text = out.get("reply", "")
        await self._send_json("turn_end", {"reply_text": reply_text})
        self.turns_completed += 1
        tail = splitter.finish()
        if tail and gen == self._turn_gen:
            await self._speak_sentence(gen, tail)
        await self._end_speaking()

    async def _speak_sentence(self, gen: int, text: str) -> None:
        """Sintetiza UNA oración ya cerrada sobre la conexión TTS
        persistente y reenvía su audio hasta el ack `Flushed` de Deepgram —
        así el audio de la primera oración arranca sin esperar el resto de
        la respuesta. `gen` es el `_speak_gen` vigente al momento de
        encolarla: si un barge-in lo invalida, el drenaje corta al toque."""
        if not text:
            return
        if not self.assistant_speaking:
            self.assistant_speaking = True
            try:
                await self._send_json("assistant_speaking_start", {})
            except Exception:
                pass
        self._last_spoken_text = (self._last_spoken_text + " " + text).strip()
        try:
            await self._tts.speak(text)
            await self._tts.flush()
            async for kind, chunk in self._tts.messages():
                if gen != self._speak_gen:
                    return
                if kind == "audio":
                    await self.ws.send_bytes(chunk)
                elif kind == "flushed":
                    return
        except Exception as exc:
            log.warning("fallo en TTS: %s", exc)
            try:
                await self._send_json("error", {"message": "Deepgram TTS no disponible"})
            except Exception:
                pass

    async def _end_speaking(self) -> None:
        if self.assistant_speaking:
            self.assistant_speaking = False
            try:
                await self._send_json("assistant_speaking_end", {})
            except Exception:
                pass

    async def _cleanup(self) -> None:
        self._turn_gen += 1
        self._speak_gen += 1
        if self._turn_task and not self._turn_task.done():
            self._turn_task.cancel()
        await self.stt.close()
        try:
            await self._tts.close()
        except Exception:
            pass
        try:
            await self.ws.close()
        except RuntimeError:
            pass  # ya estaba cerrado


@router.websocket("/ws/voice/live")
async def voice_live(ws: WebSocket) -> None:
    await VoiceSession(ws).run()
