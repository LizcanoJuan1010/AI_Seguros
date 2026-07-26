"""Tests de `DeepgramVoiceAgent` (voice_live.py) — Fase 1 de
openspec/changes/voice-agent-migration: la clase nueva, todavía SIN
wireado a `VoiceSession`. Dobles del WebSocket, sin red real."""
import json

import pytest

from app import config, voice_live

pytestmark = pytest.mark.unit


class FakeAgentConnection:
    """Doble mínimo de websockets.ClientConnection para el Voice Agent."""

    def __init__(self, incoming=None):
        self.sent = []
        self.closed = False
        self._incoming = list(incoming or [])

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    async def recv(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


def test_settings_message_endpoint_present_with_deepseek_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    agent = voice_live.DeepgramVoiceAgent(system_prompt="prompt de prueba")

    settings = agent._settings_message()

    think = settings["agent"]["think"]
    assert think["provider"] == {"type": "groq", "model": "deepseek-v4-flash"}
    assert think["endpoint"]["url"] == "https://api.deepseek.com/chat/completions"
    assert think["endpoint"]["headers"]["authorization"] == "Bearer test-key"
    assert think["prompt"] == "prompt de prueba"


def test_settings_message_no_endpoint_without_deepseek_key(monkeypatch):
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    agent = voice_live.DeepgramVoiceAgent(system_prompt="prompt de prueba")

    settings = agent._settings_message()

    assert "endpoint" not in settings["agent"]["think"]


def test_settings_message_functions_have_no_client_side_field():
    """`client_side` rompe el parseo de Deepgram (verificado en el spike) —
    nunca debe aparecer en las funciones que mandamos en Settings."""
    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")

    settings = agent._settings_message()

    functions = settings["agent"]["think"]["functions"]
    assert functions == voice_live._VOICE_FUNCTIONS
    assert all("client_side" not in f for f in functions)


def test_settings_message_excludes_tools_that_make_no_sense_by_voice():
    """Las tools de gerente (que `_exec_tool` rechazaría en voz alta) y las
    que piden file_id (imposible hablando) no viajan al Voice Agent."""
    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")

    nombres = {f["name"] for f in agent._settings_message()["agent"]["think"]["functions"]}

    assert nombres.isdisjoint(voice_live._NO_VOICE_TOOLS)
    # Las del flujo de venta del cliente siguen presentes.
    assert {"cotizar", "emitir_poliza", "capturar_datos_cliente"} <= nombres


async def test_events_yields_audio_for_binary_messages():
    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")
    agent._ws = FakeAgentConnection(incoming=[b"\x00\x01", b"\x02\x03"])

    events = [e async for e in agent.events()]

    assert events == [("audio", b"\x00\x01"), ("audio", b"\x02\x03")]


async def test_events_yields_type_and_full_message_for_json():
    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")
    payload = {"type": "ConversationText", "role": "user", "content": "hola"}
    agent._ws = FakeAgentConnection(incoming=[json.dumps(payload)])

    events = [e async for e in agent.events()]

    assert events == [("ConversationText", payload)]


async def test_connect_raises_when_settings_rejected(monkeypatch):
    """Si Deepgram rechaza el Settings, `connect()` debe fallar explícito —
    no dejar la sesión en un estado a medio conectar."""
    welcome = json.dumps({"type": "Welcome"})
    error = json.dumps({"type": "Error", "code": "UNPARSABLE_CLIENT_MESSAGE"})
    fake = FakeAgentConnection(incoming=[welcome, error])

    async def fake_connect(url, **kwargs):
        return fake

    monkeypatch.setattr(voice_live.websockets, "connect", fake_connect)
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "fake-key")

    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")
    with pytest.raises(RuntimeError, match="rechazó"):
        await agent.connect()


async def test_respond_function_call_sends_expected_shape():
    agent = voice_live.DeepgramVoiceAgent(system_prompt="x")
    agent._ws = FakeAgentConnection()

    await agent.respond_function_call("call_1", "cotizar", {"opciones": []})

    sent = json.loads(agent._ws.sent[0])
    assert sent == {"type": "FunctionCallResponse", "id": "call_1",
                    "name": "cotizar", "content": json.dumps({"opciones": []})}
