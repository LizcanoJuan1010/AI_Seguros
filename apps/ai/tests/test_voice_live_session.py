"""Tests de `VoiceSession` (arquitectura Voice Agent de Deepgram) con
dobles — sin red real a Deepgram ni a Postgres. `asyncio_mode = auto`
(pytest.ini) detecta las funciones `async def` solas, sin marcar cada una.

Reemplaza la suite vieja de `DeepgramSTT`/`DeepgramTTS`/`looks_like_echo`
(arquitectura anterior, borrada — ver openspec/changes/voice-agent-migration).
La clase de transporte (`DeepgramVoiceAgent`) tiene su propia suite en
test_voice_agent.py; acá se prueba la ORQUESTACIÓN de `VoiceSession`
(traducción de eventos, barge-in, ejecución de herramientas) con `_agent`
mockeado.
"""
import asyncio
import json
from unittest.mock import AsyncMock

from app import voice_live


class FakeClientWebSocket:
    """Doble mínimo de fastapi.WebSocket — solo lo que VoiceSession usa."""

    def __init__(self):
        self.sent_json = []
        self.sent_bytes = []
        self.closed_code = None

    async def send_json(self, data):
        self.sent_json.append(data)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def close(self, code=1000):
        self.closed_code = code


async def test_authenticate_success_sets_identity_and_sends_auth_ok(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    claims = {"sub": "user-1", "teamId": "tenant-1", "role": "cliente", "type": "access"}
    ws.receive_json = AsyncMock(return_value={"type": "auth", "data": {"token": "tok"}})
    monkeypatch.setattr(voice_live.auth, "decode_token", lambda t: claims)

    ok = await session.authenticate()

    assert ok is True
    assert session.user_id == "web:user-1"
    assert session.tenant_id == "tenant-1"
    assert ws.sent_json[-1] == {"type": "auth_ok", "data": {}}


async def test_authenticate_rejects_invalid_token(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    ws.receive_json = AsyncMock(return_value={"type": "auth", "data": {"token": "bad"}})
    monkeypatch.setattr(voice_live.auth, "decode_token", lambda t: None)

    ok = await session.authenticate()

    assert ok is False
    assert ws.sent_json[-1]["type"] == "auth_error"


async def test_barge_in_notifies_client_and_stops_speaking():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = True

    await session._barge_in()

    assert session.assistant_speaking is False
    assert ws.sent_json[-1] == {"type": "barge_in", "data": {}}


async def test_client_loop_forwards_audio_to_agent():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session._agent = AsyncMock()

    pcm = b"\x01\x02"
    ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "bytes": pcm},
        {"type": "websocket.disconnect"},
    ])

    await session._client_loop()

    session._agent.send_audio.assert_awaited_once_with(pcm)


async def test_client_loop_respects_mute():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session._agent = AsyncMock()

    ws.receive = AsyncMock(side_effect=[
        {"type": "websocket.receive", "text": json.dumps({"type": "mute"})},
        {"type": "websocket.receive", "bytes": b"\x01\x02"},
        {"type": "websocket.disconnect"},
    ])

    await session._client_loop()

    session._agent.send_audio.assert_not_awaited()
    assert session.muted is True


async def test_handle_agent_event_audio_forwards_bytes():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    await session._handle_agent_event("audio", b"\x00\x01")

    assert ws.sent_bytes == [b"\x00\x01"]


async def test_handle_agent_event_user_text_emits_transcript_and_remembers(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.user_id = "web:u"
    session.tenant_id = "t"
    remember_calls = []

    async def fake_remember(user_id, content, tenant_id):
        remember_calls.append((user_id, content, tenant_id))

    monkeypatch.setattr(voice_live, "_remember", fake_remember)

    await session._handle_agent_event(
        "ConversationText", {"role": "user", "content": "quiero un seguro de vida"})
    await asyncio.sleep(0)  # _remember se dispara como task de fondo

    assert {"type": "transcript_final", "data": {"text": "quiero un seguro de vida"}} in ws.sent_json
    assert remember_calls == [("web:u", "quiero un seguro de vida", "t")]


async def test_handle_agent_event_user_text_while_ai_speaking_triggers_barge_in(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = True
    monkeypatch.setattr(voice_live, "_remember", AsyncMock())

    await session._handle_agent_event("ConversationText", {"role": "user", "content": "espera"})

    assert session.assistant_speaking is False
    assert {"type": "barge_in", "data": {}} in ws.sent_json


async def test_handle_agent_event_assistant_text_emits_token():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    await session._handle_agent_event(
        "ConversationText", {"role": "assistant", "content": "¡Hola!"})

    assert {"type": "token", "data": {"text": "¡Hola!"}} in ws.sent_json


async def test_handle_agent_event_user_started_speaking_triggers_barge_in():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = True

    await session._handle_agent_event("UserStartedSpeaking", {"type": "UserStartedSpeaking"})

    assert session.assistant_speaking is False
    assert {"type": "barge_in", "data": {}} in ws.sent_json


async def test_handle_agent_event_user_started_speaking_noop_if_ai_silent():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = False

    await session._handle_agent_event("UserStartedSpeaking", {"type": "UserStartedSpeaking"})

    assert not any(m["type"] == "barge_in" for m in ws.sent_json)


async def test_handle_agent_event_error_notifies_client_without_raising():
    """`FAILED_TO_THINK` (observado de forma intermitente en el spike) no
    debe tumbar la sesión — solo se traduce a un evento `error`."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    await session._handle_agent_event(
        "Error", {"type": "Error", "description": "Failed to think. Please check your agent.think settings."})

    assert {"type": "error", "data": {
        "message": "Failed to think. Please check your agent.think settings."}} in ws.sent_json


async def test_handle_function_call_executes_tool_and_responds(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.user_id = "web:u"
    session.tenant_id = "t"
    session.role = "cliente"
    session._agent = AsyncMock()

    fake_result = {"opciones": [{"quote_id": "q1"}]}
    captured_args = {}

    def fake_exec_tool(name, args, **kwargs):
        captured_args["name"] = name
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs
        return fake_result

    monkeypatch.setattr(voice_live, "_exec_tool", fake_exec_tool)

    await session._handle_function_call({
        "id": "call_1", "name": "cotizar",
        "arguments": json.dumps({"country": "CO", "tipo": "vida"}),
    })

    assert captured_args["name"] == "cotizar"
    assert captured_args["args"] == {"country": "CO", "tipo": "vida"}
    assert captured_args["kwargs"] == {"phone": "web:u", "role": "cliente", "tenant_id": "t"}
    assert {"type": "tool_start", "data": {
        "tool": "cotizar", "args": {"country": "CO", "tipo": "vida"}}} in ws.sent_json
    assert any(m["type"] == "tool_result" and m["data"]["tool"] == "cotizar" for m in ws.sent_json)
    session._agent.respond_function_call.assert_awaited_once_with("call_1", "cotizar", fake_result)


async def test_handle_function_call_tool_exception_does_not_raise(monkeypatch):
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session._agent = AsyncMock()

    def failing_tool(name, args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(voice_live, "_exec_tool", failing_tool)

    await session._handle_function_call({"id": "call_1", "name": "cotizar", "arguments": "{}"})

    session._agent.respond_function_call.assert_awaited_once()
    call_args = session._agent.respond_function_call.call_args.args
    assert call_args[0] == "call_1"
    assert call_args[1] == "cotizar"
    assert "error" in call_args[2]


async def test_cleanup_closes_agent_and_websocket():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session._agent = AsyncMock()

    await session._cleanup()

    session._agent.close.assert_awaited_once()
    assert ws.closed_code == 1000


async def test_cleanup_without_agent_still_closes_websocket():
    """`_agent` puede seguir en `None` si `run()` corta antes de conectar
    (ej. sin DEEPSEEK_API_KEY) — `_cleanup` no debe romper por eso."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    await session._cleanup()

    assert ws.closed_code == 1000
