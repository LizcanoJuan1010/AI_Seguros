"""WebSocket de voz en tiempo real (/ws/voice/live) — una sola conexión al
Voice Agent de Deepgram (STT+LLM+TTS administrado por ellos), en vez de
orquestar STT/TTS/DeepSeek por separado (arquitectura vieja, ver
openspec/changes/live-call-deepgram y live-call-voice-quality). El LLM
sigue siendo DeepSeek (conectado como proveedor `think` custom) y las
herramientas son las mismas de `agent_core.TOOLS_SCHEMA` — cambia CÓMO se
orquesta la conversación, no la lógica de negocio.

Solo lo consume el gateway WS de NestJS (nunca el navegador directo) — Nest
relaya audio binario + frames JSON en ambas direcciones sin transformarlos.
Este módulo NO escribe en Postgres (AiCall/CallMessage): esa persistencia
la hace Nest espiando `transcript_final`/`turn_end`.

Protocolo completo y qué se verificó EMPÍRICAMENTE contra la API real
(la doc pública de Deepgram no traía un ejemplo completo para este caso):
openspec/changes/voice-agent-spike/, openspec/changes/voice-agent-migration/design.md
"""
import asyncio
import json
import logging
import uuid
from typing import AsyncIterator, Optional

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from . import auth, config, memory
from .agent_core import SYSTEM_PROMPT_VOICE, VOICE_AGENT_FUNCTIONS, _exec_tool
from .assistant import _remember

log = logging.getLogger("seguria.voice_live")
router = APIRouter()

_AUTH_TIMEOUT_S = 10


def _parse_sse_frame(frame: str) -> Optional[tuple[str, dict]]:
    """Parsea 'event: X\\ndata: {json}\\n\\n' (formato de `_frame` en
    assistant.py) de vuelta a (event, data) — se reusa para traducir la
    salida de `_checkout_frames`/`_summarize_tool` (chat web) a eventos del
    canal de voz sin duplicar esa lógica."""
    lines = frame.strip("\n").split("\n")
    if len(lines) != 2 or not lines[0].startswith("event: ") or not lines[1].startswith("data: "):
        return None
    event = lines[0][len("event: "):]
    try:
        data = json.loads(lines[1][len("data: "):])
    except json.JSONDecodeError:
        return None
    return event, data


_VOICE_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"


class DeepgramVoiceAgent:
    """Conexión ÚNICA al Voice Agent de Deepgram (STT+LLM+TTS en un solo
    WebSocket) — reemplaza las viejas `DeepgramSTT`+`DeepgramTTS`+el loop
    `_run_llm`/`_run_demo` de `VoiceSession` (ver
    openspec/changes/voice-agent-migration). `VoiceSession._agent_loop`
    traduce sus eventos nativos al vocabulario que ya consume el frontend.
    Detalle completo del protocolo y qué se verificó empíricamente (la doc
    pública de Deepgram no traía un ejemplo completo para este caso): ver
    ese change.

    Puntos que NO calzan con lo que dice la doc pública, confirmados contra
    la API real:
      - Auth: `Authorization: Token <key>` (la doc dice Bearer; con Bearer
        la API real devuelve 401).
      - Endpoint: `/v1/agent/converse` (`wss://agent.deepgram.com` solo da 404).
      - `think.endpoint` (LLM custom) va HERMANO de `think.provider`, NO
        anidado adentro — anidado, Deepgram rechaza con
        `UNPARSABLE_CLIENT_MESSAGE` sin importar el `provider.type` usado.
      - `functions` es flat (`name`/`description`/`parameters`) — el campo
        `client_side` NO va en la función (Deepgram lo agrega él mismo en
        el `FunctionCallRequest`; incluirlo en Settings rompe el parseo).
      - `FunctionCallRequest` anida las llamadas en un array `functions`
        (cada una con `id`/`name`/`arguments` — `arguments` es un STRING
        JSON, no un dict).
    """

    def __init__(self, *, system_prompt: str) -> None:
        self._ws = None
        self._system_prompt = system_prompt

    def _settings_message(self) -> dict:
        think: dict = {
            "provider": {"type": "groq", "model": config.DEEPSEEK_MODEL},
            "prompt": self._system_prompt,
            "functions": VOICE_AGENT_FUNCTIONS,
        }
        if config.DEEPSEEK_API_KEY:
            # `type: "groq"` es arbitrario entre los no-managed: Deepgram
            # solo lo usa para la convención de auth del `endpoint`, no
            # restringe qué proveedor real hay detrás de la URL (verificado
            # — DeepSeek funciona así, y no aparece como type nombrado).
            think["endpoint"] = {
                "url": f"{config.DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions",
                "headers": {"authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
            }
        return {
            "type": "Settings",
            "audio": {
                "input": {"encoding": "linear16", "sample_rate": 16000},
                "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
            },
            "agent": {
                "language": "es",
                "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
                "think": think,
                "speak": {"provider": {"type": "deepgram", "model": config.DEEPGRAM_VOICE_MODEL}},
            },
        }

    async def connect(self) -> None:
        self._ws = await websockets.connect(
            _VOICE_AGENT_URL,
            additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
        )
        await self._ws.recv()  # Welcome — no trae nada que necesitemos.
        await self._ws.send(json.dumps(self._settings_message()))
        reply = json.loads(await self._ws.recv())
        if reply.get("type") != "SettingsApplied":
            raise RuntimeError(f"Voice Agent rechazó la configuración: {reply}")

    async def send_audio(self, chunk: bytes) -> None:
        """Deepgram puede cerrar la conexión de su lado en cualquier
        momento (ej. tras un `FAILED_TO_THINK` — observado en pruebas
        reales). Un chunk de audio perdido justo en ese instante no debe
        tumbar `_client_loop` con un traceback; `events()` ya se entera del
        cierre por su cuenta y termina la sesión con normalidad."""
        if self._ws is None:
            return
        try:
            await self._ws.send(chunk)
        except ConnectionClosed:
            pass

    async def inject_user_message(self, content: str) -> None:
        """Solo para pruebas (sin audio real) — ver voice-agent-spike."""
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({"type": "InjectUserMessage", "content": content}))
        except ConnectionClosed:
            pass

    async def respond_function_call(self, call_id: str, name: str, result) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps({
                "type": "FunctionCallResponse", "id": call_id, "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str)[:6000],
            }))
        except ConnectionClosed:
            pass

    async def close(self) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.close()
        except Exception:
            pass
        self._ws = None

    async def events(self) -> AsyncIterator[tuple[str, dict | bytes]]:
        """Yields (kind, payload): `kind` es el `type` nativo del mensaje
        (`ConversationText`, `FunctionCallRequest`, `UserStartedSpeaking`,
        `Error`, `History`, ...) o `"audio"` con los bytes crudos de TTS.

        `FAILED_TO_THINK` (falla llamando al LLM) se observó en pruebas
        reales — y a diferencia de otros `Error`, Deepgram cierra la
        conexión completa justo después (no es un error recuperable a
        mitad de sesión). El llamador recibe el `Error` para avisarle al
        usuario, y este generador termina solo (`ConnectionClosed`) apenas
        después — `VoiceSession` no necesita lógica extra para notarlo."""
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
                yield msg.get("type", "Unknown"), msg
        except ConnectionClosed:
            return


class VoiceSession:
    """Estado por conexión: auth -> conecta al Voice Agent -> loop de
    eventos -> limpieza. El Voice Agent resuelve STT+LLM(DeepSeek)+TTS en
    una sola conexión — ya no orquestamos rondas de tool-calling nosotros
    (eso era `_run_llm`/`_run_demo`, que este canal ya no usa)."""

    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.session_id = str(uuid.uuid4())
        self.user_id = ""
        self.tenant_id = ""
        self.role = "cliente"
        self.muted = False
        self.assistant_speaking = False
        self.turns_completed = 0
        self._agent: Optional[DeepgramVoiceAgent] = None

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
        if not config.DEEPGRAM_API_KEY or not config.DEEPSEEK_API_KEY:
            # El Voice Agent NO tiene un "modo demo" como el chat de texto:
            # sin DeepSeek real, Deepgram rechaza el Settings (probado en el
            # spike — "model not available" sin el endpoint que lo redirige).
            await self._send_json("auth_error", {"reason": "Voice Agent no configurado"})
            await self.ws.close(code=1011)
            return
        if not await self.authenticate():
            await self.ws.close(code=4401)
            return

        mem_ctx = await memory.get_memory_context(self.user_id, tenant_id=self.tenant_id)
        system_prompt = f"{SYSTEM_PROMPT_VOICE}\n\n{mem_ctx}" if mem_ctx else SYSTEM_PROMPT_VOICE
        self._agent = DeepgramVoiceAgent(system_prompt=system_prompt)
        try:
            await self._agent.connect()
        except Exception as exc:
            log.warning("no se pudo conectar al Voice Agent: %s", exc)
            await self._send_json("error", {"message": "Deepgram no disponible"})
            await self.ws.close(code=1011)
            return

        agent_task = asyncio.create_task(self._agent_loop())
        client_task = asyncio.create_task(self._client_loop())
        _done, pending = await asyncio.wait(
            {agent_task, client_task}, return_when=asyncio.FIRST_COMPLETED
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
                        await self._agent.send_audio(data)
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

    async def _agent_loop(self) -> None:
        """Traduce los eventos nativos del Voice Agent al MISMO vocabulario
        que ya consume el frontend (`useLiveVoiceCall.ts`) — cero cambios
        ahí. Un hiccup puntual (reenviar audio, un `Error` del agente) no
        debe tumbar toda la llamada; solo se corta si la conexión al Voice
        Agent misma se cae (`events()` termina)."""
        async for kind, payload in self._agent.events():
            try:
                await self._handle_agent_event(kind, payload)
            except Exception:
                log.warning("fallo manejando evento %s del Voice Agent", kind, exc_info=True)

    async def _handle_agent_event(self, kind: str, payload) -> None:
        if kind == "audio":
            await self.ws.send_bytes(payload)
            return
        if kind == "ConversationText":
            role = payload.get("role")
            content = payload.get("content", "")
            if role == "user":
                await self._send_json("transcript_final", {"text": content})
                if self.assistant_speaking:
                    await self._barge_in()
                asyncio.create_task(_remember(self.user_id, content, self.tenant_id))
            elif role == "assistant":
                await self._send_json("token", {"text": content})
            return
        if kind == "UserStartedSpeaking":
            if self.assistant_speaking:
                await self._barge_in()
            return
        if kind == "FunctionCallRequest":
            for call in payload.get("functions", []):
                await self._handle_function_call(call)
            return
        if kind == "Error":
            log.warning("Voice Agent error: %s", payload)
            await self._send_json("error", {
                "message": payload.get("description") or "Error del agente de voz"})
            return
        # AgentAudioDone (fin de turno hablado), History, Welcome,
        # SettingsApplied, etc.: sin acción por ahora — ver Open Questions
        # en openspec/changes/voice-agent-migration/design.md.

    async def _handle_function_call(self, call: dict) -> None:
        from .assistant import _checkout_frames, _summarize_tool

        name = call.get("name")
        call_id = call.get("id")
        try:
            args = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        await self._send_json("tool_start", {"tool": name, "args": args})
        try:
            result = await asyncio.to_thread(
                _exec_tool, name, args, phone=self.user_id, role=self.role,
                tenant_id=self.tenant_id)
        except Exception as exc:
            log.exception("tool %s falló", name)
            result = {"error": f"la herramienta falló: {exc}"}
        summary, meta = _summarize_tool(name, result)
        await self._send_json("tool_result", {"tool": name, "summary": summary, "meta": meta})
        for frame in _checkout_frames(name, result):
            parsed = _parse_sse_frame(frame)
            if parsed:
                await self._send_json(*parsed)
        await self._agent.respond_function_call(call_id, name, result)

    async def _barge_in(self) -> None:
        """El usuario empezó a hablar mientras la IA sonaba: avisa al
        frontend para que corte la reproducción. El Voice Agent maneja la
        interrupción de su lado (a confirmar con una llamada real — ver
        Open Questions del design.md)."""
        self.assistant_speaking = False
        await self._send_json("barge_in", {})

    async def _cleanup(self) -> None:
        if self._agent is not None:
            try:
                await self._agent.close()
            except Exception:
                pass
        try:
            await self.ws.close()
        except RuntimeError:
            pass  # ya estaba cerrado


@router.websocket("/ws/voice/live")
async def voice_live(ws: WebSocket) -> None:
    await VoiceSession(ws).run()
