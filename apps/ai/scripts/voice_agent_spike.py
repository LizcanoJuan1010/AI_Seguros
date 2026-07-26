"""Spike descartable: valida si el Voice Agent de Deepgram (STT+LLM+TTS en
una sola conexión, wss://agent.deepgram.com/v1/agent/converse) acepta
DeepSeek como LLM `think` custom y la herramienta `cotizar` como función —
antes de comprometerse a migrar `apps/ai/app/voice_live.py` entero.

Ver openspec/changes/voice-agent-spike/proposal.md. Este script NO se
integra a voice_live.py ni al flujo real de llamadas — es solo para correr
a mano y leer el resultado.

Protocolo verificado EMPÍRICAMENTE contra la API real de Deepgram (jul
2026) — la doc pública no traía un ejemplo completo para este caso, así que
esto se confirmó probando contra `wss://agent.deepgram.com/v1/agent/converse`
directo, no asumido de la doc:
  - Auth: `Authorization: Token <DEEPGRAM_API_KEY>` (NO "Bearer" — a pesar
    de que la doc pública dice Bearer, la API real devuelve 401 con Bearer
    y acepta con Token, igual que STT/TTS).
  - Endpoint: `/v1/agent/converse` (la raíz `wss://agent.deepgram.com` sola
    da 404).
  - Tras conectar: el server manda `Welcome`; el cliente manda `Settings`
    ANTES de cualquier audio; el server responde `SettingsApplied` o
    `Error` con `code`/`description` concretos.
  - `think.endpoint` (para un LLM no-managed) va como HERMANO de
    `think.provider`, NO anidado dentro de `provider` — con `endpoint`
    dentro de `provider` Deepgram rechaza con `UNPARSABLE_CLIENT_MESSAGE`
    sin importar el `type` usado. `provider.type` puede ser cualquiera de
    los no-managed (se probó con `"groq"`) apuntando a
    `api.deepseek.com/chat/completions` — Deepgram solo usa `type` para la
    convención de auth, no restringe el proveedor real detrás de la URL.
  - El array `functions` dentro de `think` es FLAT (`name`/`description`/
    `parameters`, igual que el schema de tools de OpenAI que ya usamos en
    `TOOLS_SCHEMA`) — el schema completo de `cotizar` (enums, objeto
    anidado `extras`, `additionalProperties`) se probó tal cual y Deepgram
    lo acepta.
  - `client_side` NO es un campo de la función: incluirlo ahí hace que
    Deepgram rechace el Settings entero con `UNPARSABLE_CLIENT_MESSAGE`.
    No hay ninguna función "cotizar" propia de Deepgram, así que cualquier
    función que declaremos le llega al cliente como `FunctionCallRequest`.
  - `FunctionCallRequest` real: `{"type": "FunctionCallRequest", "functions":
    [{"id": "call_...", "name": "cotizar", "arguments": "<json string>",
    "client_side": true}]}` — las llamadas van en un array `functions`, NO
    al nivel superior del mensaje (`id`/`name`/`arguments` de cada una).
  - `FunctionCallResponse` que Deepgram SÍ acepta: `{"type":
    "FunctionCallResponse", "id": <mismo id>, "name": <mismo name>,
    "content": <json string del resultado>}` — probado end-to-end con
    `_exec_tool("cotizar", ...)` real contra Postgres.
  - `InjectUserMessage` (`{"type": "InjectUserMessage", "content": "..."}`)
    simula texto hablado por el usuario SIN audio real — permite probar el
    turno completo (function-calling incluido) sin grabar audio.

RESULTADOS MEDIDOS (jul 2026, DeepSeek `deepseek-v4-flash` — ver nota sobre
"deepseek-chat" deprecado más abajo), un solo turno de prueba:
  - Primer byte de audio de respuesta: ~1.9s desde el mensaje inyectado.
  - `FunctionCallRequest` de `cotizar`: ~3.7s desde el mensaje inyectado.
  - El agente ejecutó `cotizar` de verdad, recibió el resultado real de
    Postgres, y siguió la conversación de forma coherente pidiendo el dato
    que le faltaba. Function-calling end-to-end funciona.

HALLAZGO APARTE (no es del spike, es un bug real de producción): la API de
DeepSeek devuelve 400 para el modelo `"deepseek-chat"` — "The supported API
model names are deepseek-v4-pro or deepseek-v4-flash". Si el `.env` real no
sobreescribe `DEEPSEEK_MODEL`, CUALQUIER llamada real a DeepSeek (voz, chat
web, WhatsApp) fallaba. Corregido el default en `apps/ai/app/config.py` a
`deepseek-v4-flash`.

Uso:
    DEEPGRAM_API_KEY=... DEEPSEEK_API_KEY=... .venv/bin/python scripts/voice_agent_spike.py

Sin DEEPSEEK_API_KEY: igual valida conexión + Settings sin `endpoint`
(degradación graciosa, mismo criterio que el resto del proyecto), pero no
se puede probar una conversación real de punta a punta.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import websockets

from app import config
from app.agent_core import TOOLS_SCHEMA, _exec_tool

_AGENT_URL = "wss://agent.deepgram.com/v1/agent/converse"
_COTIZAR_SCHEMA = next(t["function"] for t in TOOLS_SCHEMA if t["function"]["name"] == "cotizar")


def _think_block() -> dict:
    """`endpoint` es HERMANO de `provider` dentro de `think`, NO anidado
    adentro de `provider` — verificado empíricamente (con `endpoint` dentro
    de `provider`, Deepgram rechaza el Settings con UNPARSABLE_CLIENT_MESSAGE
    sin importar el `type` usado; como hermano, `SettingsApplied`). `type`
    puede ser cualquiera de los no-managed (ej. `groq`) — Deepgram solo lo
    usa para la convención de auth, no restringe al proveedor real detrás
    del `endpoint.url`."""
    think: dict = {
        "provider": {"type": "groq", "model": config.DEEPSEEK_MODEL},
        "prompt": "Eres una asesora de seguros. Usa la función cotizar para dar precios.",
        "functions": [_COTIZAR_SCHEMA],
    }
    if config.DEEPSEEK_API_KEY:
        think["endpoint"] = {
            "url": "https://api.deepseek.com/chat/completions",
            "headers": {"authorization": f"Bearer {config.DEEPSEEK_API_KEY}"},
        }
    return think


def _redact_secrets(settings: dict) -> dict:
    """Copia del Settings con headers de auth tapados — solo para loguear;
    nunca imprimir la key de DeepSeek en claro."""
    out = json.loads(json.dumps(settings))
    headers = out.get("agent", {}).get("think", {}).get("endpoint", {}).get("headers")
    if headers:
        for k in headers:
            headers[k] = "***REDACTED***"
    return out


def _settings_message() -> dict:
    return {
        "type": "Settings",
        "tags": ["spike", "voice-agent-latency"],
        "audio": {
            "input": {"encoding": "linear16", "sample_rate": 16000},
            "output": {"encoding": "linear16", "sample_rate": 24000, "container": "none"},
        },
        "agent": {
            "language": "es",
            "listen": {"provider": {"type": "deepgram", "model": "nova-3"}},
            "think": _think_block(),
            "speak": {"provider": {"type": "deepgram", "model": config.DEEPGRAM_VOICE_MODEL}},
        },
    }


async def run_spike() -> None:
    if not config.DEEPGRAM_API_KEY:
        print("FALTA DEEPGRAM_API_KEY — no se puede ni conectar. Abortando.")
        return
    if not config.DEEPSEEK_API_KEY:
        print("AVISO: falta DEEPSEEK_API_KEY — se valida conexión/Settings, "
              "pero NO se puede probar una conversación real (Deepgram no "
              "podría autenticarse contra DeepSeek de nuestra parte).")

    t0 = time.monotonic()
    async with websockets.connect(
        _AGENT_URL, additional_headers={"Authorization": f"Token {config.DEEPGRAM_API_KEY}"},
    ) as ws:
        t_connected = time.monotonic()
        print(f"[{t_connected - t0:.3f}s] conectado a {_AGENT_URL}")

        welcome_raw = await ws.recv()
        welcome = json.loads(welcome_raw)
        print(f"[{time.monotonic() - t0:.3f}s] recibido: {welcome.get('type')} — {welcome}")

        settings = _settings_message()
        await ws.send(json.dumps(settings))
        print(f"[{time.monotonic() - t0:.3f}s] Settings enviado:")
        print(json.dumps(_redact_secrets(settings), indent=2, ensure_ascii=False))

        try:
            reply_raw = await asyncio.wait_for(ws.recv(), timeout=10)
        except asyncio.TimeoutError:
            print("TIMEOUT esperando respuesta a Settings (10s) — Deepgram no contestó nada.")
            return
        reply = json.loads(reply_raw) if isinstance(reply_raw, str) else {"type": "<binario>"}
        print(f"[{time.monotonic() - t0:.3f}s] respuesta a Settings: {reply.get('type')} — {reply}")

        if reply.get("type") == "Error":
            print("\nRESULTADO: Deepgram RECHAZÓ la configuración — ver el mensaje de "
                  "error arriba para saber qué campo no calzó.")
            return
        if reply.get("type") != "SettingsApplied":
            print(f"\nRESULTADO: respuesta inesperada ({reply.get('type')}) — revisar a mano.")
            return

        print("\nSettings aceptado. Sin DEEPSEEK_API_KEY no tiene sentido seguir "
              "(el think fallaría al primer mensaje)." if not config.DEEPSEEK_API_KEY
              else "\nSettings aceptado — inyectando mensaje de usuario simulado "
              "(sin audio real, vía InjectUserMessage) para medir el turno completo.")
        if not config.DEEPSEEK_API_KEY:
            return

        await _run_simulated_turn(ws, t0)


async def _run_simulated_turn(ws, t0: float) -> None:
    """Manda `InjectUserMessage` (texto, sin audio) simulando que el cliente
    pidió una cotización, responde el `FunctionCallRequest` de `cotizar`
    ejecutando la herramienta REAL (misma `_exec_tool` que usa voice_live.py
    hoy), y mide tiempos hasta el primer byte de audio de la respuesta."""
    t_inject = time.monotonic()
    await ws.send(json.dumps({
        "type": "InjectUserMessage",
        "content": "Quiero cotizar un seguro de vida en Colombia, tengo 30 años",
    }))
    print(f"[{t_inject - t0:.3f}s] InjectUserMessage enviado")

    t_function_call = None
    t_first_audio = None
    got_function_call = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        except asyncio.TimeoutError:
            break
        if isinstance(raw, (bytes, bytearray)):
            if t_first_audio is None:
                t_first_audio = time.monotonic()
                print(f"[{t_first_audio - t0:.3f}s] primer byte de audio de respuesta "
                      f"({t_first_audio - t_inject:.3f}s desde el InjectUserMessage)")
            continue
        msg = json.loads(raw)
        mtype = msg.get("type")
        if mtype == "FunctionCallRequest":
            t_function_call = time.monotonic()
            print(f"[{t_function_call - t0:.3f}s] FunctionCallRequest recibido "
                  f"({t_function_call - t_inject:.3f}s desde el InjectUserMessage): {msg}")
            got_function_call = True
            # El request anida las llamadas en un array `functions` (cada una
            # con id/name/arguments) — NO al nivel superior del mensaje.
            for call in msg.get("functions", []):
                await _respond_function_call(ws, call)
        elif mtype in ("ConversationText", "AgentThinking", "UserStartedSpeaking"):
            print(f"[{time.monotonic() - t0:.3f}s] {mtype}: {msg}")
        elif mtype == "AgentAudioDone":
            print(f"[{time.monotonic() - t0:.3f}s] AgentAudioDone — turno terminado")
            break
        elif mtype == "Error":
            print(f"[{time.monotonic() - t0:.3f}s] Error del servidor: {msg}")
            break

    print("\n--- Resumen del turno simulado ---")
    print("FunctionCallRequest de cotizar recibido:", got_function_call)
    print("Primer byte de audio recibido:", t_first_audio is not None)
    if t_function_call:
        print(f"Latencia hasta FunctionCallRequest: {t_function_call - t_inject:.3f}s")
    if t_first_audio:
        print(f"Latencia hasta primer audio: {t_first_audio - t_inject:.3f}s")


async def _respond_function_call(ws, call: dict) -> None:
    """Ejecuta `cotizar` de verdad (misma `_exec_tool` que usa el agente hoy
    contra Postgres) y responde con `FunctionCallResponse`. `call` es UNA
    entrada del array `functions` del `FunctionCallRequest` (id/name/arguments)."""
    func = call.get("name")
    call_id = call.get("id")
    args_raw = call.get("arguments") or {}
    if isinstance(args_raw, str):
        try:
            args_raw = json.loads(args_raw)
        except json.JSONDecodeError:
            args_raw = {}
    try:
        result = _exec_tool(func, args_raw, phone="spike-test", role="cliente", tenant_id="demo")
    except Exception as exc:
        result = {"error": str(exc)}
    await ws.send(json.dumps({
        "type": "FunctionCallResponse",
        "id": call_id,
        "name": func,
        "content": json.dumps(result, ensure_ascii=False, default=str)[:6000],
    }))
    print(f"FunctionCallResponse enviado para {func} (call_id={call_id})")


if __name__ == "__main__":
    asyncio.run(run_spike())
