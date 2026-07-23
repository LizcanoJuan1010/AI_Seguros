"""Cliente delgado hacia el backend NestJS (Prisma) para el registro
unificado de sesiones multicanal (`ai_calls`/`call_messages`).

Mismo patrón que `_emitir_poliza` en `agent_core.py`: reenvía `X-Tenant-Id`,
timeout corto y degrada en silencio si el backend no responde — nunca debe
romper ni frenar el streaming del chat. Los valores de `channel` deben ser
los del enum Prisma `Channel` tal cual (`WHATSAPP`, `WEB_CHAT`, `EMAIL`,
`VOICE_CALL`), no los `@map` en minúscula de la base de datos.
"""
import logging

import requests

from .config import BACKEND_URL

log = logging.getLogger(__name__)

_TIMEOUT = 5


def open_session(tenant_id: str, phone: str, channel: str) -> str | None:
    """Resuelve/crea el Customer por teléfono y reutiliza o abre la AiCall de
    ese (tenant, phone, channel) — la regla de qué cuenta como "misma sesión"
    vive en el backend (`AiCallsService.openSession`). Devuelve el `id` de la
    AiCall, o `None` si el backend no respondió."""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/ai-calls/sessions",
            json={"phone": phone, "channel": channel},
            timeout=_TIMEOUT,
            headers={"X-Tenant-Id": tenant_id},
        )
        resp.raise_for_status()
        return resp.json().get("id")
    except Exception as exc:
        log.warning("no se pudo abrir sesión en el backend (%s): %s", channel, exc)
        return None


def post_call_message(tenant_id: str, ai_call_id: str, speaker: str, content: str) -> None:
    """Registra un turno en `call_messages`. Silencioso ante fallos (best-effort)."""
    try:
        resp = requests.post(
            f"{BACKEND_URL}/api/v1/call-messages",
            json={"callId": ai_call_id, "speaker": speaker, "content": content[:4000]},
            timeout=_TIMEOUT,
            headers={"X-Tenant-Id": tenant_id},
        )
        resp.raise_for_status()
    except Exception as exc:
        log.warning("no se pudo registrar call_message: %s", exc)


def log_turn(tenant_id: str, phone: str, channel: str, role: str, message: str) -> None:
    """Abre/reutiliza la sesión y registra el mensaje en una sola llamada de
    conveniencia. `role` usa el vocabulario del chat (`cliente`/`asistente`/
    `gerente`); se traduce al `SpeakerType` del backend (`IA`/`CLIENTE`)."""
    if not message:
        return
    ai_call_id = open_session(tenant_id, phone, channel)
    if not ai_call_id:
        return
    speaker = "IA" if role == "asistente" else "CLIENTE"
    post_call_message(tenant_id, ai_call_id, speaker, message)
