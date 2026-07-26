"""Tests de `voice_live._parse_sse_frame` — el puente entre los frames SSE
que ya produce `assistant.py` (`_frame`) y los frames JSON del WS de voz.

Nota: el resto de `voice_live.py` (DeepgramSTT/TTS, VoiceSession) es
inherentemente async/I-O (sockets salientes a Deepgram) — su cobertura con
un servidor Deepgram simulado se cubre en la Fase 5 (Testing) del change
live-call-deepgram, que agrega pytest-asyncio. Esta función pura sí se
puede probar hoy, sin infraestructura nueva.
"""
import json

from app.voice_live import _parse_sse_frame


def test_parse_sse_frame_valid_returns_event_and_data():
    frame = 'event: token\ndata: {"text": "hola"}\n\n'

    result = _parse_sse_frame(frame)

    assert result == ("token", {"text": "hola"})


def test_parse_sse_frame_matches_real_frame_helper_output():
    """Triangulación con un evento/payload distinto, generado con el mismo
    formato que `assistant._frame` (event/data en dos líneas + json.dumps)."""
    event, payload = "tool_result", {"tool": "cotizar", "summary": "3 opciones cotizadas", "meta": {"n": 3}}
    frame = f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    result = _parse_sse_frame(frame)

    assert result == (event, payload)


def test_parse_sse_frame_rejects_malformed_input():
    assert _parse_sse_frame("linea suelta sin el formato esperado") is None


def test_parse_sse_frame_rejects_invalid_json_data():
    assert _parse_sse_frame("event: token\ndata: {no es json}\n\n") is None
