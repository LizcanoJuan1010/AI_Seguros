"""Test de integración del endpoint REAL `/ws/voice/live` (no solo la clase
`VoiceSession` aislada como en test_voice_live_session.py) — ejercita el
ASGI/WebSocket real de FastAPI vía `TestClient`, con el Voice Agent de
Deepgram stubbeado (monkeypatch de `websockets.connect`, sin red).

Usa una app FastAPI MÍNIMA que monta solo `voice_live.router` — NO
`app.main:app` completo: su `lifespan` llama `init_db()`/`memory.init_pool()`
y se queda colgado sin Postgres/Redis reales disponibles. El router en sí
no depende de esas conexiones (memoria degrada a dict en proceso sin pool),
así que probarlo aislado es correcto y evita esa dependencia.

Alcance deliberadamente acotado: prueba handshake + auth + forwarding de
audio hacia el stub del Voice Agent. NO prueba el relay cruzado
Nest<->Python de punta a punta (requeriría levantar los dos runtimes
conectados por red real) ni una conversación completa con DeepSeek real —
eso se prueba a mano (ver openspec/changes/voice-agent-migration/tasks.md,
Fase 3).
"""
import asyncio
import json
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, config, voice_live

app = FastAPI()
app.include_router(voice_live.router)


class FakeVoiceAgentConnection:
    """Doble del WebSocket del Voice Agent — a diferencia del doble en
    test_voice_live_session.py (lista ya poblada de antemano), acá
    `recv()`/`__anext__` esperan sobre una `asyncio.Queue` real: el
    servidor corre en OTRO hilo/loop que el test (TestClient), así que hace
    falta una espera de verdad, no una lista fija.

    Se precarga con `Welcome` + `SettingsApplied` — `DeepgramVoiceAgent.
    connect()` los espera en ese orden vía `recv()` explícito antes de
    seguir (handshake: recv Welcome, send Settings, recv SettingsApplied)."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._queue.put_nowait(json.dumps({"type": "Welcome"}))
        self._queue.put_nowait(json.dumps({"type": "SettingsApplied"}))

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True
        self._queue.put_nowait(None)

    async def recv(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()


def _make_token() -> str:
    payload = {
        "sub": "user-1",
        "email": "cliente@tequendama.co",
        "role": "cliente",
        "teamId": "tenant-1",
        "type": "access",
        "exp": time.time() + 3600,
    }
    return auth._jwt_encode(payload, config.JWT_SECRET)


def test_voice_live_endpoint_auth_and_audio_forwarding(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "fake-key-para-el-test")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    # El servidor corre en otro hilo (TestClient) — un threading.Event (no
    # asyncio.Event) es la forma correcta de sincronizar con el hilo del test.
    audio_received = threading.Event()

    class RecordingConnection(FakeVoiceAgentConnection):
        async def send(self, data):
            await super().send(data)
            if isinstance(data, (bytes, bytearray)):
                audio_received.set()

    agent_connection = RecordingConnection()

    async def fake_connect(url, **kwargs):
        assert url == voice_live._VOICE_AGENT_URL
        return agent_connection

    monkeypatch.setattr(voice_live.websockets, "connect", fake_connect)

    token = _make_token()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            ws.send_json({"type": "auth", "data": {"token": token}})
            assert ws.receive_json() == {"type": "auth_ok", "data": {}}

            pcm_chunk = b"\x01\x02\x03\x04"
            ws.send_bytes(pcm_chunk)
            assert audio_received.wait(timeout=2), "el audio nunca llegó al stub del Voice Agent"

    assert pcm_chunk in agent_connection.sent


def test_voice_live_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "fake-key-para-el-test")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            ws.send_json({"type": "auth", "data": {"token": "no-es-un-jwt-valido"}})
            msg = ws.receive_json()

    assert msg["type"] == "auth_error"


def test_voice_live_endpoint_without_deepgram_key_rejects(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "fake-deepseek-key")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "auth_error"


def test_voice_live_endpoint_without_deepseek_key_rejects(monkeypatch):
    """El Voice Agent no tiene un "modo demo": sin DeepSeek real, Deepgram
    rechazaría el Settings (verificado en voice-agent-spike) — se corta
    antes, con el mismo `auth_error` que sin DEEPGRAM_API_KEY."""
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "fake-key-para-el-test")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "auth_error"
