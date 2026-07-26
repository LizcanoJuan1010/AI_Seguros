"""Tests de `_load_history`/`_append_history` (`agent_core.py`) — la ventana
de historial de sesión en Postgres (`chat_history`).

Corren contra la Postgres real de la suite (ver conftest.py); no son
`unit` puros porque tocan la base, pero no dependen de infraestructura de
Deepgram/DeepSeek — cambio `live-call-voice-quality`, spec `voice-live-call`,
requisito "Continuidad de contexto conversacional".
"""
import uuid

from app.agent_core import _append_history, _load_history


def _tool_round(i: int) -> list[dict]:
    """Un par assistant(tool_calls)+tool, como los que genera un turno con
    herramientas encadenadas en `_run_llm`."""
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": f"call_{i}", "type": "function",
             "function": {"name": "cotizar", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": f"call_{i}", "content": "{}"},
    ]


def test_load_history_survives_long_tool_call_sequence():
    """20 rondas de herramientas (40 filas) tras el único mensaje `user`
    empujan ese `user` fuera de cualquier ventana razonable — el historial
    NO debe degradar a `[]` mientras exista un cierre de turno real."""
    session_id = f"test:{uuid.uuid4()}"
    _append_history(session_id, [{"role": "user", "content": "Hola, quiero un seguro de vida"}])
    for i in range(20):
        _append_history(session_id, _tool_round(i))
    _append_history(session_id, [{"role": "assistant", "content": "Aquí tienes tus opciones."}])

    history = _load_history(session_id)

    assert history != []
    assert history[-1] == {"role": "assistant", "content": "Aquí tienes tus opciones."}


def test_load_history_prefers_earliest_safe_anchor_over_later_user():
    """Con un cierre de turno (`assistant` sin tool_calls) y un `user`
    posterior, ambos dentro de la ventana, el historial debe arrancar en el
    ancla MÁS TEMPRANA (el assistant cerrado) para conservar más contexto —
    no solo en el `user` más reciente, que es lo único que el código viejo
    reconocía como ancla segura."""
    session_id = f"test:{uuid.uuid4()}"
    for i in range(5):
        _append_history(session_id, _tool_round(i))
    closing = {"role": "assistant", "content": "Primera respuesta cerrada."}
    _append_history(session_id, [closing])
    _append_history(session_id, [{"role": "user", "content": "Otra pregunta"}])
    for i in range(5, 10):
        _append_history(session_id, _tool_round(i))
    _append_history(session_id, [{"role": "assistant", "content": "Segunda respuesta cerrada."}])

    history = _load_history(session_id)

    assert history[0] == closing
