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
import time
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
# Handshake contra Deepgram (Welcome/SettingsApplied). Sin límite, una cuenta
# sin el Agents Platform habilitado (acepta el WS pero nunca contesta) dejaba
# la llamada colgada PARA SIEMPRE en "Conectando…" — exactamente el escenario
# "recién puse la API key". El spike de referencia usaba 10 s.
_CONNECT_TIMEOUT_S = 10

# Herramientas que NO se le ofrecen al agente de voz. Las de gerente porque
# `_exec_tool` igual las rechaza ("acceso denegado") y el agente leería ese
# rechazo en voz alta; `analizar_documento` porque pide un file_id que en una
# llamada no existe (no hay forma de subir archivos hablando).
_NO_VOICE_TOOLS = {"obtener_insights", "listar_leads", "crear_campana_marketing",
                   "solicitar_informe_gerencial", "analizar_documento"}
_VOICE_FUNCTIONS = [f for f in VOICE_AGENT_FUNCTIONS if f.get("name") not in _NO_VOICE_TOOLS]


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
        # Última vez que salió audio real hacia Deepgram — lo usa el keepalive
        # para mandar silencio SOLO cuando el flujo se detuvo (mute, pestaña en
        # background). Inyectar silencio entre chunks reales metería artefactos.
        self._last_audio = 0.0
        self._keepalive_task: Optional[asyncio.Task] = None

    def _settings_message(self) -> dict:
        think: dict = {
            "provider": {"type": "groq", "model": config.DEEPSEEK_MODEL},
            "prompt": self._system_prompt,
            "functions": _VOICE_FUNCTIONS,
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
            open_timeout=_CONNECT_TIMEOUT_S,
        )
        # Welcome — no trae nada que necesitemos, pero SÍ tiene que llegar.
        await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT_S)
        await self._ws.send(json.dumps(self._settings_message()))
        reply = json.loads(await asyncio.wait_for(self._ws.recv(), timeout=_CONNECT_TIMEOUT_S))
        if reply.get("type") != "SettingsApplied":
            raise RuntimeError(f"Voice Agent rechazó la configuración: {reply}")
        self._last_audio = time.monotonic()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _keepalive_loop(self) -> None:
        """Deepgram corta con CLIENT_MESSAGE_TIMEOUT a los ~10-12 s sin audio
        (confirmado empíricamente en el spike — ver design.md de
        voice-agent-migration). Con el mic silenciado (o la pestaña en
        background) el navegador deja de mandar frames y la llamada moría
        sola. Cada 4 s sin audio real se manda ~100 ms de silencio linear16
        @16 kHz — el mecanismo que el spike verificó, a diferencia del
        mensaje KeepAlive JSON, que no se probó contra la API real."""
        silence = b"\x00" * 3200  # 100 ms de PCM16 mono a 16 kHz
        try:
            while self._ws is not None:
                await asyncio.sleep(2)
                if self._ws is None:
                    return
                if time.monotonic() - self._last_audio > 4:
                    try:
                        await self._ws.send(silence)
                        self._last_audio = time.monotonic()
                    except ConnectionClosed:
                        return
        except asyncio.CancelledError:
            return

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
            self._last_audio = time.monotonic()
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
        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None
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
        # Texto acumulado del turno actual del asistente — viaja en `turn_end`
        # para que Nest persista el lado de la IA (CallMessage). Sin esto, en
        # Postgres solo quedaba el lado del cliente.
        self._reply_text = ""
        # Refs de tasks fire-and-forget (_remember, tools): sin referencia
        # fuerte, el GC puede matarlas a mitad de camino.
        self._bg_tasks: set[asyncio.Task] = set()

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    async def _send_json(self, type_: str, data: dict) -> None:
        await self.ws.send_json({"type": type_, "data": data})

    async def authenticate(self) -> bool:
        """Primer frame: `{"type":"auth","data":{...}}` con `token` (staff) o
        `device_id` (cliente final anónimo).

        El cliente final no tiene usuario — su identidad es el `device_id` del
        navegador, el mismo que ya ancla memoria y leads en el chat web, así
        que la llamada continúa la conversación que esa persona ya tuvo. Quien
        decide si el anónimo puede entrar es el gateway de Nest (valida formato
        y topes, ver live-call.gateway.ts): aquí solo se confía en lo que llega
        de él, igual que el resto de rutas servicio-a-servicio del stack."""
        try:
            raw = await asyncio.wait_for(self.ws.receive_json(), timeout=_AUTH_TIMEOUT_S)
            if raw.get("type") != "auth":
                raise ValueError("se esperaba el frame 'auth' primero")
            data = raw.get("data") or {}
            token = data.get("token", "")
            device_id = str(data.get("device_id") or "").strip()
            claims = auth.decode_token(token) if token else None
            if not claims and not device_id:
                raise ValueError("token inválido o expirado")
        except Exception as exc:
            try:
                await self._send_json("auth_error", {"reason": str(exc)})
            except Exception:
                pass
            return False

        if claims:
            self.user_id = f"web:{claims['sub']}"
            self.tenant_id = claims.get("teamId") or config.DEMO_TENANT_ID
            self.role = "gerente" if claims.get("role") in {"GERENTE", "ADMIN"} else "cliente"
        else:
            self.user_id = f"web:{device_id}"
            self.tenant_id = config.DEMO_TENANT_ID
            self.role = "cliente"
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
        # Espera la cancelación de verdad: sin esto, _cleanup cerraba el WS
        # con la task aún en vuelo ("Task was destroyed but it is pending").
        await asyncio.gather(*pending, return_exceptions=True)
        for task in list(self._bg_tasks):
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
                try:
                    control = json.loads(text)
                except json.JSONDecodeError:
                    # Un frame malformado no debe tumbar la llamada entera.
                    log.debug("frame de control no-JSON ignorado")
                    continue
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
                # `thinking` resetea el buffer del subtítulo en el frontend
                # (useLiveVoiceCall): sin esto, el caption CONCATENABA todos
                # los turnos del asistente desde el inicio de la llamada.
                await self._send_json("thinking", {})
                if self.assistant_speaking:
                    await self._barge_in()
                self._spawn(_remember(self.user_id, content, self.tenant_id))
            elif role == "assistant":
                self._reply_text += content
                await self._send_json("token", {"text": content})
            return
        if kind == "UserStartedSpeaking":
            if self.assistant_speaking:
                await self._barge_in()
            return
        if kind == "AgentStartedSpeaking":
            # Sin esta transición el barge-in estaba MUERTO (assistant_speaking
            # jamás pasaba a True) y la UI nunca mostraba a la IA hablando.
            self.assistant_speaking = True
            await self._send_json("assistant_speaking_start", {})
            return
        if kind == "AgentAudioDone":
            self.assistant_speaking = False
            self.turns_completed += 1
            await self._send_json("assistant_speaking_end", {})
            # Nest espía `turn_end` para persistir el turno de la IA
            # (recordAssistantTurn) — sin esto el transcript quedaba a medias.
            await self._send_json("turn_end", {"reply": self._reply_text})
            self._reply_text = ""
            return
        if kind == "FunctionCallRequest":
            for call in payload.get("functions", []):
                # En task aparte: una tool lenta (emitir_poliza -> HTTP 8 s)
                # ejecutada en serie BLOQUEABA el relay de audio — el relleno
                # hablado del agente se cortaba a mitad de palabra.
                self._spawn(self._handle_function_call(call))
            return
        if kind == "Warning":
            # Cuota, modelo deprecado, voz degradada… — antes se tragaba en
            # silencio y el síntoma aparecía después sin pista alguna.
            log.warning("Voice Agent warning: %s", payload)
            return
        if kind == "Error":
            log.warning("Voice Agent error: %s", payload)
            await self._send_json("error", {
                "message": payload.get("description") or "Error del agente de voz"})
            return
        if kind in {"Welcome", "SettingsApplied", "History"}:
            return
        log.debug("evento del Voice Agent sin manejar: %s", kind)

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
