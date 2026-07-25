"""Tests de VoiceSession/DeepgramSTT/DeepgramTTS con dobles — sin red real
a Deepgram ni al agente RAG (Postgres). `asyncio_mode = auto` (pytest.ini)
detecta las funciones `async def` solas, sin marcar cada una.

Nota: igual que test_voice_live.py, `conftest.py` saltea TODA la suite sin
un Postgres local en localhost:5432 (política preexistente del proyecto,
no relacionada con este archivo). Ejecución directa más abajo documentada
en el reporte de la tanda — no se modifica esa política acá.
"""
import asyncio
import json
from unittest.mock import AsyncMock

from app import voice_live
from app.voice_live import looks_like_echo


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
        self.sent_bytes = []
        self.closed_code = None

    async def send_json(self, data):
        self.sent_json.append(data)

    async def send_bytes(self, data):
        self.sent_bytes.append(data)

    async def close(self, code=1000):
        self.closed_code = code


async def test_deepgram_stt_transcripts_yields_partial_and_utterance():
    """Solo `speech_final` cierra la frase; `is_final` intermedio es partial."""
    incoming = [
        json.dumps({"type": "Metadata", "request_id": "x"}),
        json.dumps({"type": "Results", "is_final": False, "speech_final": False,
                    "channel": {"alternatives": [{"transcript": "hola"}]}}),
        json.dumps({"type": "Results", "is_final": True, "speech_final": False,
                    "channel": {"alternatives": [{"transcript": "hola"}]}}),
        json.dumps({"type": "Results", "is_final": True, "speech_final": True,
                    "channel": {"alternatives": [{"transcript": "como estas"}]}}),
        json.dumps({"type": "Results", "is_final": True, "speech_final": True,
                    "channel": {"alternatives": [{"transcript": ""}]}}),
    ]
    stt = voice_live.DeepgramSTT()
    stt._ws = FakeDeepgramConnection(incoming)

    results = [r async for r in stt.transcripts()]

    assert ("partial", "hola") in results
    assert ("utterance", "hola como estas") in results
    # Sin speech_final no debe haber utterance del primer segmento solo.
    assert ("utterance", "hola") not in results


async def test_deepgram_tts_cancel_sends_clear_without_closing():
    """Conexión persistente: `cancel()` (barge-in) manda `Clear` pero NO
    cierra el socket — sigue viva para el resto de la llamada."""
    tts = voice_live.DeepgramTTS()
    fake = FakeDeepgramConnection()
    tts._ws = fake

    await tts.cancel()

    assert json.loads(fake.sent[0]) == {"type": "Clear"}
    assert fake.closed is False
    assert tts._ws is fake


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
    """Conexión persistente: barge-in llama `cancel()` (Clear) sobre la
    MISMA instancia de TTS — ya no se anula/reabre por turno."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    fake_tts = AsyncMock()
    session._tts = fake_tts
    session.assistant_speaking = True
    speak_gen_before = session._speak_gen

    await session._barge_in()

    assert session.assistant_speaking is False
    assert session._speak_gen == speak_gen_before + 1
    fake_tts.cancel.assert_awaited_once()
    assert session._tts is fake_tts
    assert ws.sent_json[-1] == {"type": "barge_in", "data": {}}


async def test_stt_loop_interim_while_speaking_barge_in_no_turn():
    """Partial con la IA hablando: corta TTS, NO arranca turno."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.assistant_speaking = True
    fake_tts = AsyncMock()
    session._tts = fake_tts

    async def fake_transcripts():
        yield "partial", "hola"

    session.stt.transcripts = fake_transcripts
    session._run_turn = AsyncMock()

    await session._stt_loop()

    fake_tts.cancel.assert_awaited_once()
    assert session.assistant_speaking is False
    assert {"type": "transcript_partial", "data": {"text": "hola"}} in ws.sent_json
    assert {"type": "barge_in", "data": {}} in ws.sent_json
    assert session._turn_task is None
    session._run_turn.assert_not_awaited()


async def test_stt_loop_starts_turn_on_utterance():
    """Solo un evento utterance (speech_final) dispara el turno."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    async def fake_transcripts():
        yield "partial", "quiero cotizar"
        yield "utterance", "quiero cotizar un seguro de auto"

    session.stt.transcripts = fake_transcripts
    session._run_turn = AsyncMock()

    await session._stt_loop()
    if session._turn_task:
        await session._turn_task

    session._run_turn.assert_awaited_once_with("quiero cotizar un seguro de auto")
    assert {"type": "transcript_final", "data": {"text": "quiero cotizar un seguro de auto"}} in ws.sent_json


async def test_stt_loop_discards_echo_of_last_spoken():
    """Utterance casi igual al último TTS no crea turno (anti-eco)."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session._last_spoken_text = (
        "¡Hola! Soy Tequendama, tu asesora de seguros. ¿En qué te ayudo hoy?"
    )

    async def fake_transcripts():
        yield "utterance", "Hola soy Tequendama tu asesora de seguros en qué te ayudo hoy"

    session.stt.transcripts = fake_transcripts
    session._run_turn = AsyncMock()

    await session._stt_loop()

    assert session._turn_task is None
    session._run_turn.assert_not_awaited()
    assert {"type": "transcript_final", "data": {
        "text": "Hola soy Tequendama tu asesora de seguros en qué te ayudo hoy",
    }} in ws.sent_json


def test_looks_like_echo_detects_overlap():
    last = "¡Hola! Soy Tequendama, tu asesora de seguros. ¿En qué te ayudo hoy?"
    assert looks_like_echo(
        "Hola soy Tequendama tu asesora de seguros en qué te ayudo hoy", last,
    )
    assert not looks_like_echo("quiero un seguro de auto para Bogotá", last)


async def test_speak_sentence_barge_in_race_cleans_without_attribute_error():
    """Barge-in a mitad de `_speak_sentence`: la conexión TTS es persistente
    (ya no se anula/reabre), pero el drenaje de `messages()` debe cortar
    apenas `_barge_in()` invalida el `_speak_gen` vigente."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)

    class SlowTTS(voice_live.DeepgramTTS):
        def __init__(self):
            super().__init__()
            self._chunks = [("audio", b"\x00\x01"), ("audio", b"\x02\x03"), ("audio", b"\x04\x05")]

        async def connect(self):
            self._ws = FakeDeepgramConnection()

        async def speak(self, text: str):
            return None

        async def flush(self):
            return None

        async def cancel(self):
            return None

        async def messages(self):
            for i, item in enumerate(self._chunks):
                if i == 1:
                    await session._barge_in()
                yield item

        async def close(self):
            self._ws = None

    session._tts = SlowTTS()
    gen = session._speak_gen

    await session._speak_sentence(gen, "texto largo de prueba para el barge-in")

    assert session.assistant_speaking is False
    assert ws.sent_bytes == [b"\x00\x01"]  # corta antes del segundo chunk
    assert {"type": "barge_in", "data": {}} in ws.sent_json
    assert {"type": "assistant_speaking_start", "data": {}} in ws.sent_json
    # No speaking_end limpio tras barge-in (el flag ya estaba en false).
    assert not any(m["type"] == "assistant_speaking_end" for m in ws.sent_json)


async def test_run_turn_cancelled_does_not_speak():
    """Turno cancelado (gen invalidado) no llama _speak_sentence ni emite turn_end."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.user_id = "web:u"
    session.tenant_id = "t"
    session._speak_sentence = AsyncMock()

    import app.voice_live as vl

    async def gen_runner(*_a, **_k):
        await asyncio.sleep(10)
        return
        yield  # pragma: no cover

    original_demo = vl._run_demo
    original_key = vl.config.DEEPSEEK_API_KEY
    original_mem = vl.memory.get_memory_context
    original_remember = vl._remember

    vl.config.DEEPSEEK_API_KEY = ""
    vl._run_demo = gen_runner
    vl.memory.get_memory_context = AsyncMock(return_value="")
    vl._remember = AsyncMock()

    try:
        task = asyncio.create_task(session._run_turn("hola"))
        await asyncio.sleep(0.05)
        session._turn_gen += 1
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0)
    finally:
        vl._run_demo = original_demo
        vl.memory.get_memory_context = original_mem
        vl._remember = original_remember
        vl.config.DEEPSEEK_API_KEY = original_key

    session._speak_sentence.assert_not_awaited()
    assert not any(m["type"] == "turn_end" for m in ws.sent_json)


async def test_run_turn_passes_voice_channel_without_hint_prefix():
    """`_run_turn` ya no antepone ningún hint de canal al transcript —
    channel='voice' selecciona el prompt de cierre completo (Camilo), que ya
    trae esas restricciones (ver SYSTEM_PROMPT_VOICE en agent_core.py). Antes
    de este cambio, `message` llevaba un prefijo `[Canal voz en vivo: ...]`
    que terminaba persistido en `chat_history` como si fuera habla real."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.user_id = "web:u"
    session.tenant_id = "t"

    import app.voice_live as vl

    received: dict = {}

    async def capture_runner(session_id, message, mem_ctx, role, user_id, tenant_id, out,
                             channel="web", history_content=None):
        received["message"] = message
        received["channel"] = channel
        received["history_content"] = history_content
        out["reply"] = "ok"
        yield 'event: done\ndata: {}\n\n'

    original_demo = vl._run_demo
    original_key = vl.config.DEEPSEEK_API_KEY
    original_mem = vl.memory.get_memory_context
    original_remember = vl._remember
    vl.config.DEEPSEEK_API_KEY = ""
    vl._run_demo = capture_runner
    vl.memory.get_memory_context = AsyncMock(return_value="")
    vl._remember = AsyncMock()
    try:
        await session._run_turn("quiero un seguro de vida")
    finally:
        vl._run_demo = original_demo
        vl.config.DEEPSEEK_API_KEY = original_key
        vl.memory.get_memory_context = original_mem
        vl._remember = original_remember

    assert received["message"] == "quiero un seguro de vida"
    assert received["channel"] == "voice"


async def test_run_turn_invalidated_gen_skips_speak_after_llm():
    """Si el gen cambia durante el LLM, no habla aunque el runner termine."""
    ws = FakeClientWebSocket()
    session = voice_live.VoiceSession(ws)
    session.user_id = "web:u"
    session.tenant_id = "t"
    session._turn_gen = 1
    session._speak_sentence = AsyncMock()

    import app.voice_live as vl

    async def quick_runner(session_id, message, mem_ctx, role, user_id, tenant_id, out,
                           channel="web", history_content=None):
        out["reply"] = "hola de nuevo"
        # Invalida el turno como haría un barge-in / nuevo final.
        session._turn_gen += 1
        yield 'event: token\ndata: {"text": "hola"}\n\n'
        yield 'event: done\ndata: {}\n\n'

    original_demo = vl._run_demo
    original_key = vl.config.DEEPSEEK_API_KEY
    original_mem = vl.memory.get_memory_context
    original_remember = vl._remember
    vl.config.DEEPSEEK_API_KEY = ""
    vl._run_demo = quick_runner
    vl.memory.get_memory_context = AsyncMock(return_value="")
    vl._remember = AsyncMock()
    try:
        await session._run_turn("eco fantasma")
    finally:
        vl._run_demo = original_demo
        vl.config.DEEPSEEK_API_KEY = original_key
        vl.memory.get_memory_context = original_mem
        vl._remember = original_remember

    session._speak_sentence.assert_not_awaited()
    assert not any(m["type"] == "turn_end" for m in ws.sent_json)
