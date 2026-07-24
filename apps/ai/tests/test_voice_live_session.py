"""Tests de VoiceSession/DeepgramSTT/DeepgramTTS con dobles — sin red real
a Deepgram ni al agente RAG (Postgres). `asyncio_mode = auto` (pytest.ini)
detecta las funciones `async def` solas, sin marcar cada una.

Nota: igual que test_voice_live.py, `conftest.py` saltea TODA la suite sin
un Postgres local en localhost:5432 (política preexistente del proyecto,
no relacionada con este archivo). Ejecución directa más abajo documentada
en el reporte de la tanda — no se modifica esa política acá.
"""
import json
from unittest.mock import AsyncMock

from app import voice_live


class FakeDeepgramConnection:
    """Doble de websockets.ClientConnection: async iterable + send/close."""

    def __init__(self, incoming=None):
        self.sent = []
        self.closed = False
        self._incoming = list(incoming or [])

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._incoming:
            raise StopAsyncIteration
        return self._incoming.pop(0)


class FakeClientWebSocket:
    """Doble mínimo de fastapi.WebSocket — solo lo que VoiceSession usa."""

    def __init__(self):
        self.sent_json = []
        self.closed_code = None

    async def send_json(self, data):
        self.sent_json.append(data)

    async def close(self, code=1000):
        self.closed_code = code


async def test_deepgram_stt_transcripts_yields_final_and_partial():
    incoming = [
        json.dumps({"type": "Metadata", "request_id": "x"}),
        json.dumps({"type": "Results", "is_final": False,
                    "channel": {"alternatives": [{"transcript": "hola"}]}}),
        json.dumps({"type": "Results", "is_final": True,
                    "channel": {"alternatives": [{"transcript": "hola como estas"}]}}),
        json.dumps({"type": "Results", "is_final": True,
                    "channel": {"alternatives": [{"transcript": ""}]}}),
    ]
    stt = voice_live.DeepgramSTT()
    stt._ws = FakeDeepgramConnection(incoming)

    results = [r async for r in stt.transcripts()]

    assert results == [(False, "hola"), (True, "hola como estas")]


async def test_deepgram_tts_cancel_sends_clear_and_closes():
    tts = voice_live.DeepgramTTS()
    fake = FakeDeepgramConnection()
    tts._ws = fake

    await tts.cancel()

    assert json.loads(fake.sent[0]) == {"type": "Clear"}
    assert fake.closed is True
    assert tts._ws is None


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


async def test_barge_in_cancels_tts_and_notifies_client():
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    fake_tts = AsyncMock()
    session._tts = fake_tts
    session.assistant_speaking = True

    await session._barge_in()

    assert session.assistant_speaking is False
    fake_tts.cancel.assert_awaited_once()
    assert session._tts is None
    assert ws.sent_json[-1] == {"type": "barge_in", "data": {}}


async def test_stt_loop_ignores_interim_transcripts_no_barge_in():
    """Spec: 'No interruption during silence' — un transcript NO final no
    debe disparar barge-in ni arrancar un turno."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = True
    fake_tts = AsyncMock()
    session._tts = fake_tts

    async def fake_transcripts():
        yield False, "hola"

    session.stt.transcripts = fake_transcripts

    await session._stt_loop()

    fake_tts.cancel.assert_not_awaited()
    assert session.assistant_speaking is True
    assert {"type": "transcript_partial", "data": {"text": "hola"}} in ws.sent_json
    assert session._turn_task is None


async def test_stt_loop_starts_turn_on_final_transcript():
    """Spec: 'User interrupts the agent' / turno normal — un transcript
    final dispara un turno con ese texto."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    async def fake_transcripts():
        yield True, "quiero cotizar un seguro de auto"

    session.stt.transcripts = fake_transcripts
    session._run_turn = AsyncMock()

    await session._stt_loop()
    if session._turn_task:
        await session._turn_task

    session._run_turn.assert_awaited_once_with("quiero cotizar un seguro de auto")
    assert {"type": "transcript_final", "data": {"text": "quiero cotizar un seguro de auto"}} in ws.sent_json
