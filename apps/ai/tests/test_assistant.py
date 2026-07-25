"""Tests de `assistant.py` — cambio `live-call-voice-quality`, spec
`voice-live-call`, requisitos "Sin saludo repetido" y "Continuidad de
contexto conversacional": el hint de canal (voz) no debe quedar mezclado
con el contenido real del usuario que se persiste en `chat_history`, y el
modo demo (sin DEEPSEEK_API_KEY) no debe re-saludar en turnos posteriores."""
import uuid

import pytest

from app.agent_core import (SYSTEM_PROMPT_GERENTE, SYSTEM_PROMPT_VOICE,
                            SYSTEM_PROMPT_WEB, _append_history, _load_history)
from app.assistant import _history_user_message, _run_demo, _select_system_prompt


@pytest.mark.unit
def test_history_user_message_uses_raw_content_when_given():
    """El canal de voz pasa el transcript crudo aparte del texto con hint
    que sí va al LLM — lo que se persiste debe ser el crudo."""
    result = _history_user_message(
        "[Canal voz en vivo: ...]\nHola, quiero un seguro de vida",
        "Hola, quiero un seguro de vida",
    )
    assert result == {"role": "user", "content": "Hola, quiero un seguro de vida"}


@pytest.mark.unit
def test_history_user_message_falls_back_to_message_without_raw_content():
    """El chat web no manda `history_content` — se persiste `message` tal cual, sin cambios."""
    result = _history_user_message("hola, quiero cotizar", None)
    assert result == {"role": "user", "content": "hola, quiero cotizar"}


@pytest.mark.unit
def test_select_system_prompt_gerente_ignores_channel():
    assert _select_system_prompt("gerente", "web") == SYSTEM_PROMPT_GERENTE
    assert _select_system_prompt("gerente", "voice") == SYSTEM_PROMPT_GERENTE


@pytest.mark.unit
def test_select_system_prompt_voice_channel_uses_closing_persona():
    assert _select_system_prompt("cliente", "voice") == SYSTEM_PROMPT_VOICE


@pytest.mark.unit
def test_select_system_prompt_web_channel_uses_sofia():
    assert _select_system_prompt("cliente", "web") == SYSTEM_PROMPT_WEB


async def _collect_demo_reply(session_id: str, message: str, tenant_id: str,
                              history_content: str | None = None) -> str:
    out: dict = {"reply": ""}
    async for _ in _run_demo(session_id, message, "", "cliente", f"web:{session_id}",
                             tenant_id, out, history_content=history_content):
        pass
    return out["reply"]


async def test_run_demo_greets_on_first_turn():
    session_id = str(uuid.uuid4())
    tenant_id = f"test-{uuid.uuid4()}"
    reply = await _collect_demo_reply(session_id, "no sé qué necesito, ayúdame", tenant_id)
    assert "Soy Tequendama" in reply


async def test_run_demo_does_not_regreet_after_first_turn():
    """Requisito 'Sin saludo repetido': con historial previo real en la
    sesión, el modo demo no debe volver a presentarse."""
    session_id = str(uuid.uuid4())
    tenant_id = f"test-{uuid.uuid4()}"
    hist_key = f"{tenant_id}:{session_id}"
    _append_history(hist_key, [{"role": "user", "content": "hola"},
                               {"role": "assistant", "content": "¡Hola! Soy Tequendama..."}])

    reply = await _collect_demo_reply(session_id, "no sé qué necesito, ayúdame", tenant_id)

    assert "Soy Tequendama" not in reply


async def test_run_demo_persists_raw_history_content_not_hinted_message():
    """El hint de canal (voz) no debe quedar mezclado con el habla real del
    cliente en `chat_history` — se persiste `history_content`, no `message`."""
    session_id = str(uuid.uuid4())
    tenant_id = f"test-{uuid.uuid4()}"
    hint = "[Canal voz en vivo: saluda una sola vez si hace falta.]\n"
    raw = "no sé qué necesito, ayúdame"

    await _collect_demo_reply(session_id, hint + raw, tenant_id, history_content=raw)

    persisted = _load_history(f"{tenant_id}:{session_id}")
    user_messages = [m["content"] for m in persisted if m["role"] == "user"]
    assert user_messages == [raw]


async def test_run_demo_three_consecutive_turns_greets_only_once():
    """Spec 'Sin saludo repetido', escenario de 3+ turnos: enlaza 3 llamadas
    reales a `_run_demo` sobre la MISMA sesión (sin seedear historial a
    mano) — solo el primer turno debe saludar."""
    session_id = str(uuid.uuid4())
    tenant_id = f"test-{uuid.uuid4()}"

    reply1 = await _collect_demo_reply(session_id, "no sé qué necesito, ayúdame", tenant_id)
    reply2 = await _collect_demo_reply(session_id, "tengo dudas todavía", tenant_id)
    reply3 = await _collect_demo_reply(session_id, "sigo sin decidirme", tenant_id)

    assert "Soy Tequendama" in reply1
    assert "Soy Tequendama" not in reply2
    assert "Soy Tequendama" not in reply3
