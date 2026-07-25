"""Test de integración del endpoint REAL `/ws/voice/live` (no solo la clase
`VoiceSession` aislada como en test_voice_live_session.py) — ejercita el
ASGI/WebSocket real de FastAPI vía `TestClient`, con Deepgram stubbeado
(monkeypatch de `websockets.connect`, sin red).

Usa una app FastAPI MÍNIMA que monta solo `voice_live.router` — NO
`app.main:app` completo: su `lifespan` llama `init_db()`/`memory.init_pool()`
y se queda colgado sin Postgres/Redis reales disponibles (confirmado en esta
sesión: `TestClient(app)` con la app completa nunca retorna). El router en
sí no depende de esas conexiones, así que probarlo aislado es correcto y
evita esa dependencia de infraestructura.

Alcance deliberadamente acotado: prueba handshake + auth + forwarding de
audio hacia el stub de Deepgram STT. NO prueba el relay cruzado
Nest<->Python de punta a punta (eso requeriría levantar los dos runtimes
—Node y Python— conectados por red real, algo que no se pudo montar ni
verificar en esta sesión). Ver el reporte de la Fase 5 para el detalle de
por qué se acotó así.

Nota: igual que los otros archivos de este directorio, `conftest.py`
saltea TODA la suite sin un Postgres local — política preexistente del
proyecto. Ejecución directa documentada en el reporte de la tanda.
"""
import asyncio
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import auth, config, voice_live

app = FastAPI()
app.include_router(voice_live.router)


class FakeDeepgramConnection:
    """A diferencia del doble en test_voice_live_session.py (lista ya
    poblada de antemano), acá `__anext__` espera sobre una `asyncio.Queue`
    real — el servidor corre en OTRO hilo/loop que el test (TestClient), así
    que hace falta una espera de verdad, no una lista fija, para no cortar
    la iteración antes de tiempo."""

    def __init__(self):
        self.sent = []
        self.closed = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True
        self._queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item


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

    # El servidor corre en otro hilo (TestClient) — un threading.Event (no
    # asyncio.Event) es la forma correcta de sincronizar con el hilo del test.
    audio_received = threading.Event()

    class RecordingConnection(FakeDeepgramConnection):
        async def send(self, data):
            await super().send(data)
            if isinstance(data, (bytes, bytearray)):
                audio_received.set()

    stt_connection = RecordingConnection()
    tts_connection = FakeDeepgramConnection()

    async def fake_connect(url, **kwargs):
        # `run()` ahora conecta STT y TTS (persistente para toda la
        # llamada) — distingue por URL cuál stub devolver.
        if url == voice_live._deepgram_listen_url():
            assert "language=" in url
            assert "model=" in url
            return stt_connection
        assert url == voice_live._deepgram_speak_url()
        return tts_connection

    monkeypatch.setattr(voice_live.websockets, "connect", fake_connect)

    token = _make_token()

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            ws.send_json({"type": "auth", "data": {"token": token}})
            assert ws.receive_json() == {"type": "auth_ok", "data": {}}

            pcm_chunk = b"\x01\x02\x03\x04"
            ws.send_bytes(pcm_chunk)
            assert audio_received.wait(timeout=2), "el audio nunca llegó al stub de Deepgram"

    assert pcm_chunk in stt_connection.sent


def test_voice_live_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "fake-key-para-el-test")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            ws.send_json({"type": "auth", "data": {"token": "no-es-un-jwt-valido"}})
            msg = ws.receive_json()

    assert msg["type"] == "auth_error"


def test_voice_live_endpoint_without_deepgram_key_rejects(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "")

    with TestClient(app) as client:
        with client.websocket_connect("/ws/voice/live") as ws:
            msg = ws.receive_json()

    assert msg["type"] == "auth_error"
