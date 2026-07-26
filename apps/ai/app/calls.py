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
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .config import (ELEVENLABS_AGENT_ID, ELEVENLABS_AGENT_PHONE_NUMBER_ID,
                     ELEVENLABS_API_KEY, ELEVENLABS_BASE_URL, ELEVENLABS_VOICE_ID)

log = logging.getLogger("seguria.calls")

_TIMEOUT = 15

# Ley 2300 de 2023 (Colombia): contacto comercial SOLO lunes a viernes
# 7:00-19:00 y sábados 8:00-15:00, por canales autorizados — nunca domingo.
# Aplica explícitamente a aseguradoras (ver
# Nota_estrategica_Seguros_Colsubsidio.pdf §6). Único choque legal para TODA
# llamada saliente (venta nueva o reactivación de checklist), sin importar
# el país del cliente — la operación comercial (Camila) es colombiana.
_TZ_COLOMBIA = ZoneInfo("America/Bogota")


def _dentro_ventana_legal(ahora: datetime | None = None) -> bool:
    ahora = (ahora or datetime.now(_TZ_COLOMBIA)).astimezone(_TZ_COLOMBIA)
    dia, hora = ahora.weekday(), ahora.hour + ahora.minute / 60
    if dia == 6:  # domingo: nunca
        return False
    if dia == 5:  # sábado
        return 8 <= hora < 15
    return 7 <= hora < 19  # lunes(0) a viernes(4)


def enabled() -> bool:
    """True si hay credenciales para llamar de verdad (agente + número + key)."""
    return bool(ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID
                and ELEVENLABS_AGENT_PHONE_NUMBER_ID)


def _edad_desde_fecha(fecha: str | None) -> int | None:
    if not fecha:
        return None
    try:
        from datetime import date, datetime
        nacimiento = datetime.strptime(str(fecha)[:10], "%Y-%m-%d").date()
        hoy = date.today()
        return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))
    except (ValueError, TypeError):
        return None


def _productos_vigentes(phone: str) -> str:
    """Pólizas VIGENTES del cliente (dominio Prisma, `public.*`) — mismo query
    que `elevenlabs.service.ts::handleInitWebhook` hace del lado NestJS para
    llamadas ENTRANTES; esto es el espejo para que las SALIENTES tengan lo
    mismo. Vacío si no hay cliente/pólizas o la consulta falla."""
    from .db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT pr.name AS nombre
               FROM public.policies p
               JOIN public.customers c ON c.id = p.customer_id
               JOIN public.quotes q ON q.id = p.quote_id
               JOIN public.products pr ON pr.id = q.product_id
               WHERE c.phone = %s AND p.status = 'VIGENTE'""", (phone,)).fetchall()
        return ", ".join(r["nombre"] for r in rows)
    except Exception:
        conn.rollback()
        return ""
    finally:
        conn.close()


def _sale_context(phone: str, tenant_id: str) -> dict[str, Any]:
    """Contexto real de venta para las `dynamic_variables` de la llamada:
    nombre, perfil (edad/afiliación/dependientes/vivienda/vehículo/tipo de
    ingreso/productos vigentes — mismos campos que ya arma
    `elevenlabs.service.ts::handleInitWebhook` para llamadas entrantes) +
    última cotización. Mismo criterio fail-open que el resto del stack: si la
    BD no responde o no hay nada todavía (lead frío que nunca cotizó), degrada
    a {} — nunca rompe el disparo de la llamada. Ver
    `reference/elevenlabs_agent_prompt.md` para el prompt del agente de voz
    que consume estas variables vía `{{...}}`."""
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
        ctx["edad"] = (_edad_desde_fecha(checkout.get("birth_date"))
                      or _edad_desde_fecha(intake.get("fecha_nacimiento")) or "")
        afiliado = intake.get("afiliado_colsubsidio")
        ctx["afiliacion"] = "afiliado" if afiliado is True else "no afiliado" if afiliado is False else ""
        ctx["dependientes"] = intake.get("dependientes") or ""
        ctx["vivienda"] = intake.get("tenencia") or ""
        if intake.get("placa"):
            ctx["vehiculo"] = f"{intake.get('marca', '')} {intake.get('modelo_anio', '')}".strip()
        ctx["tipo_ingreso"] = intake.get("actividad_economica") or ""
        ctx["productos_vigentes"] = _productos_vigentes(phone)

        from . import checklist
        conn2 = get_conn()
        try:
            chk = checklist.latest_by_session(conn2, session_key)
            if chk:
                estado = checklist.estado_actual(conn2, chk)
                ctx["paso_checklist"] = estado["paso_actual"]
                updated = chk.get("updated_at")
                if updated:
                    from datetime import datetime as _dt, timezone as _tz
                    ahora = _dt.now(_tz.utc)
                    if updated.tzinfo is None:
                        updated = updated.replace(tzinfo=_tz.utc)
                    ctx["dias_sin_avanzar"] = max(0, (ahora - updated).days)
        finally:
            conn2.close()

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
                    dynamic_variables: dict | None = None,
                    agent_id: str | None = None) -> dict:
    """Dispara una llamada saliente al `phone` indicado con el agente de voz.

    `dynamic_variables` SIEMPRE incluye `phone`/`tenant_id` (aunque quien llama
    no los pase): es la correlación que el webhook post-call usa para resolver
    el Customer/Team correctos — sin esto la llamada quedaría huérfana en el
    CRM, igual que pasaba con `conversations` antes de alinear el canal.
    También trae `_sale_context` (nombre, cotización, prima...) para que el
    agente de ElevenLabs tenga la MISMA información que ya tiene el chat de
    WhatsApp/web sin tener que preguntarla de nuevo; lo que pase explícito en
    `dynamic_variables` gana sobre lo auto-completado.

    `agent_id`: por defecto `ELEVENLABS_AGENT_ID` (Camila, reactivación de
    checklist). Pasa uno distinto para un flujo con OTRO prompt sin tocar el
    agente real — ver `ELEVENLABS_LANDING_AGENT_ID` / `landing_callback.py`.
    """
    if not _dentro_ventana_legal():
        log.info("fuera de la ventana legal de contacto (Ley 2300/2023): no se llama a %s", phone)
        return {"ok": False, "demo": False,
               "error": "fuera de la ventana horaria legal de contacto comercial "
                        "(Ley 2300/2023: lun-vie 7:00-19:00, sáb 8:00-15:00, hora Colombia)"}

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
        "agent_id": agent_id or ELEVENLABS_AGENT_ID,
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


def iniciar_llamada_reactivacion_checklist(phone: str, tenant_id: str) -> dict:
    """Llamada de reactivación para un checklist estancado (ver
    `proactive.checklist_nudges` / skill `reactivar-checklist`).

    A diferencia de `iniciar_llamada`, primero reenvía el link del checklist
    (rotando su token — el crudo no es recuperable de la fila, ver
    `checklist.reenviar_paso_actual`) para que un WhatsApp fresco le llegue al
    cliente justo antes/durante la llamada; Camila puede decir "te acabo de
    reenviar el link" en vez de leer una URL en voz."""
    from . import checklist
    from .db import get_conn

    session_key = f"{tenant_id}:{phone}"
    conn = get_conn()
    try:
        row = checklist.latest_by_session(conn, session_key)
        if row is None:
            return {"ok": False, "error": "el cliente no tiene un checklist de activación"}
        checklist.reenviar_paso_actual(conn, row)
    finally:
        conn.close()
    return iniciar_llamada(phone, tenant_id)
