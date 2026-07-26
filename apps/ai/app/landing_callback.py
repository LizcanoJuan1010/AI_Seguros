"""Puerta de entrada anónima de la landing: "déjanos tu número y te llamamos"
(ver `apps/frontend/src/features/landing/CallMeBack.tsx`).

Versión de PRUEBA: dispara la llamada con LA MISMA arquitectura de llamadas
salientes que ya usa la reactivación de checklist (`calls.iniciar_llamada`),
pero con un agente/prompt distinto (`ELEVENLABS_LANDING_AGENT_ID` — Camila
en modo informativo/venta de primer contacto, ver
`reference/elevenlabs_landing_test_prompt.md`), para no tocar el agente real
de reactivación mientras se prueba.

Deliberadamente NO trae el resto de la infraestructura de abuso que sí
necesitaría una versión de producción (verificación OTP, límites por IP/
dispositivo, tabla de auditoría) — hoy el freno natural es que la cuenta de
Twilio en trial solo marca a números verificados a mano. Endurecer esto es
trabajo aparte, fuera de alcance de esta prueba.
"""
import logging
import re

from fastapi import APIRouter
from pydantic import BaseModel

from .config import DEMO_TENANT_ID, ELEVENLABS_LANDING_AGENT_ID, PUBLIC_BASE_URL

log = logging.getLogger("seguria.landing_callback")

router = APIRouter()

# Chip del formulario -> tipo real del catálogo (coinciden literal, "otro"
# y vacío quedan sin filtro: recommend() trae las mejores opciones parejas).
_INTERES_A_TIPO = {"vida": "vida", "auto": "auto", "salud": "salud", "hogar": "hogar"}


def _enviar_ficha_previa(phone: str, interes: str | None, nombre: str | None) -> None:
    """Ficha PDF de referencia (no personalizada — todavía no hubo
    conversación) para que la persona tenga algo concreto en WhatsApp ANTES
    de que Camila la llame (ver CIERRE del prompt de prueba: ya asume que
    esto llegó). Best-effort: un fallo aquí nunca debe bloquear la llamada."""
    try:
        from .db import get_conn
        from .documents import build_quote_pdf
        from .quoting import recommend
        from . import whatsapp_gateway

        conn = get_conn()
        try:
            opciones = recommend(conn, country="CO", tipo=_INTERES_A_TIPO.get((interes or "").lower()),
                                 age=None, sum_assured_usd=None, budget_monthly_usd=None,
                                 extras={}, max_options=1)
        finally:
            conn.close()
        if not opciones:
            return
        quote = opciones[0]
        quote.pop("breakdown", None)
        path = build_quote_pdf(quote, {"name": nombre} if nombre else None, es_afiliado=False)

        from pathlib import Path
        pdf_url = f"{PUBLIC_BASE_URL}/api/documents/{Path(path).name}"
        whatsapp_gateway.enviar_documento(
            phone, pdf_url, Path(path).name,
            caption=f"Antes de llamarte: una idea de {quote['producto']} — Tequendama Seguros")
    except Exception:
        log.warning("no se pudo enviar la ficha previa a %s", phone, exc_info=True)


class CallbackRequest(BaseModel):
    telefono: str
    nombre: str | None = None
    interes: str | None = None
    device_id: str | None = None
    consent: bool = False


def _normaliza_e164(telefono: str) -> str | None:
    """Acepta "300 123 4567" o "+57 300 123 4567" → "+573001234567".
    Colombia-only (celular de 10 dígitos que empieza en 3) — coincide con el
    "+57" fijo que ya muestra CallMeBack.tsx junto al campo del formulario."""
    digitos = re.sub(r"\D", "", telefono or "")
    if digitos.startswith("57") and len(digitos) == 12 and digitos[2] == "3":
        return f"+{digitos}"
    if len(digitos) == 10 and digitos.startswith("3"):
        return f"+57{digitos}"
    return None


@router.post("/api/callback/solicitar")
def solicitar_callback(req: CallbackRequest) -> dict:
    """Contrato estable con CallMeBack.tsx: SIEMPRE 200, `ok=false` +
    `mensaje` para que los rechazos de validación se pinten bajo el campo sin
    sacar al visitante del formulario (nunca un HTTPException 4xx aquí)."""
    if not req.consent:
        return {"ok": False, "mensaje": "Necesitamos tu autorización para poder llamarte "
                                        "(Ley 1581 de 2012)."}
    phone = _normaliza_e164(req.telefono)
    if not phone:
        return {"ok": False, "mensaje": "Revisa tu número — debe ser un celular "
                                        "colombiano de 10 dígitos."}

    _enviar_ficha_previa(phone, req.interes, req.nombre)

    from . import calls
    try:
        resultado = calls.iniciar_llamada(
            phone, DEMO_TENANT_ID,
            dynamic_variables={
                "nombre_cliente": (req.nombre or "").strip(),
                "interes_declarado": req.interes or "",
                "device_id": req.device_id or "",
                "origen": "landing_callback",
            },
            agent_id=ELEVENLABS_LANDING_AGENT_ID,
        )
    except Exception:
        log.exception("no se pudo iniciar la llamada de prueba desde la landing")
        return {"ok": False, "mensaje": "No pudimos iniciar la llamada en este momento; "
                                       "intenta de nuevo en unos minutos."}

    if not resultado.get("ok", True):
        # p.ej. fuera de la ventana legal de contacto (Ley 2300/2023)
        return {"ok": False, "mensaje": resultado.get("error") or
                "No pudimos iniciar la llamada en este momento."}

    mensaje = ("Solicitud registrada (modo demo: no se marca de verdad todavía)."
              if resultado.get("demo") else
              "Te estamos llamando — contesta en unos segundos.")
    return {"ok": True, "demo": bool(resultado.get("demo")), "mensaje": mensaje}
