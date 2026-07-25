"""Motor de llamadas telefónicas salientes — ElevenLabs Conversational AI.

Dispara una llamada real (Twilio o SIP trunk nativo, según lo configurado en
el dashboard de ElevenLabs) con el agente `ELEVENLABS_AGENT_ID`. Las
`dynamic_variables` (phone/tenant_id) viajan en la llamada y vuelven en el
webhook post-call (`POST /api/v1/elevenlabs/webhook` del backend), que es
quien resuelve el Customer y registra la sesión (`AiCall` channel=voice_call)
— este módulo solo la INICIA; el registro del resultado ya vive en el backend.

Sin ELEVENLABS_API_KEY/AGENT_ID/AGENT_PHONE_NUMBER_ID corre en modo demo
(igual que Wompi/DeepSeek en el resto del stack): no llama a nadie, degrada
limpio con `{"demo": True}` en vez de romper el flujo.
"""
import logging

import requests

from .config import (ELEVENLABS_AGENT_ID, ELEVENLABS_AGENT_PHONE_NUMBER_ID,
                     ELEVENLABS_API_KEY, ELEVENLABS_BASE_URL, ELEVENLABS_VOICE_ID)

log = logging.getLogger("seguria.calls")

_TIMEOUT = 15


def enabled() -> bool:
    """True si hay credenciales para llamar de verdad (agente + número + key)."""
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID
                and ELEVENLABS_AGENT_PHONE_NUMBER_ID)


def _sale_context(phone: str, tenant_id: str) -> dict[str, Any]:
    """Contexto real de venta para las `dynamic_variables` de la llamada:
    nombre y datos ya capturados en el chat (checkout/intake) + última
    cotización (producto, aseguradora, prima). Mismo criterio fail-open que
    el resto del stack: si la BD no responde o no hay nada todavía (lead
    frío que nunca cotizó), degrada a {} — nunca rompe el disparo de la
    llamada. Ver `reference/elevenlabs_agent_prompt.md` para el prompt del
    agente de voz que consume estas variables vía `{{...}}`."""
    ctx: dict[str, Any] = {}
    try:
        from .agent_core import _get_checkout, _get_intake
        from .assistant import _latest_quote_for
        from .db import get_conn

        session_key = f"{tenant_id}:{phone}"
        conn = get_conn()
        try:
            checkout = _get_checkout(conn, session_key)
            intake = _get_intake(conn, session_key)
        finally:
            conn.close()
        quote = _latest_quote_for(phone)

        ctx["nombre_cliente"] = checkout.get("full_name") or intake.get("nombre_completo") or ""
        ctx["ciudad"] = checkout.get("city") or intake.get("ciudad") or ""
        if quote:
            ctx["tipo_seguro"] = quote.get("tipo") or ""
            ctx["producto"] = quote.get("producto") or ""
            ctx["aseguradora"] = quote.get("aseguradora") or ""
            ctx["prima_mensual_local"] = quote.get("premium_monthly_local") or ""
            ctx["moneda"] = quote.get("currency") or ""
            ctx["quote_id"] = quote.get("id") or ""
    except Exception:
        log.debug("no se pudo construir el contexto de venta para la llamada", exc_info=True)
    return {k: v for k, v in ctx.items() if v not in (None, "")}


def iniciar_llamada(phone: str, tenant_id: str, *, first_message: str | None = None,
                    dynamic_variables: dict | None = None) -> dict:
    """Dispara una llamada saliente al `phone` indicado con el agente de voz.

    `dynamic_variables` SIEMPRE incluye `phone`/`tenant_id` (aunque quien llama
    no los pase): es la correlación que el webhook post-call usa para resolver
    el Customer/Team correctos — sin esto la llamada quedaría huérfana en el
    CRM, igual que pasaba con `conversations` antes de alinear el canal.
    También trae `_sale_context` (nombre, cotización, prima...) para que el
    agente de ElevenLabs tenga la MISMA información que ya tiene el chat de
    WhatsApp/web sin tener que preguntarla de nuevo; lo que pase explícito en
    `dynamic_variables` gana sobre lo auto-completado.
    """
    variables = {"phone": phone, "tenant_id": tenant_id,
                 **_sale_context(phone, tenant_id), **(dynamic_variables or {})}

    if not enabled():
        log.info("modo demo: simula llamada a %s (tenant=%s)", phone, tenant_id)
        return {"ok": True, "demo": True, "conversation_id": None, "call_sid": None,
                "mensaje": "Llamada simulada (faltan credenciales de ElevenLabs)."}

    client_data: dict = {"dynamic_variables": variables}
    override: dict = {}
    if first_message:
        override["agent"] = {"first_message": first_message}
    if ELEVENLABS_VOICE_ID:
        override["tts"] = {"voice_id": ELEVENLABS_VOICE_ID}
    if override:
        client_data["conversation_config_override"] = override

    payload = {
        "agent_id": ELEVENLABS_AGENT_ID,
        "agent_phone_number_id": ELEVENLABS_AGENT_PHONE_NUMBER_ID,
        "to_number": phone,
        "conversation_initiation_client_data": client_data,
    }
    try:
        resp = requests.post(
            f"{ELEVENLABS_BASE_URL}/v1/convai/twilio/outbound-call",
            json=payload, timeout=_TIMEOUT,
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json() or {}
        log.info("llamada iniciada a %s: conversation_id=%s", phone, data.get("conversation_id"))
        return {"ok": bool(data.get("success", True)), "demo": False,
                "conversation_id": data.get("conversation_id"),
                "call_sid": data.get("callSid"), "mensaje": data.get("message")}
    except Exception as exc:
        log.warning("no se pudo iniciar la llamada a %s: %s", phone, exc)
        return {"ok": False, "demo": False, "error": str(exc)}
