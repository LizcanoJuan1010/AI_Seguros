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

from fastapi import APIRouter, Request
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


@router.post("/api/callback/solicitar")
def solicitar_callback(req: CallbackRequest, request: Request) -> dict:
    """Contrato estable con CallMeBack.tsx: SIEMPRE 200, `ok=false` +
    `mensaje` para que los rechazos de validación se pinten bajo el campo sin
    sacar al visitante del formulario (nunca un HTTPException 4xx aquí).

    La validación del número, el rastro auditable del consentimiento y los
    topes por hora viven en `callback.py` — esta puerta es anónima y sin eso
    sirve para hostigar a un tercero con nuestra cuenta de telefonía pagando."""
    from . import callback as guard
    from .db import get_conn

    if not req.consent:
        return {"ok": False, "mensaje": "Necesitamos tu autorización para poder llamarte "
                                        "(Ley 1581 de 2012)."}
    phone = guard.normalizar_telefono(req.telefono)
    if not phone or not guard.es_celular_colombiano(phone):
        return {"ok": False, "mensaje": "Revisa tu número — debe ser un celular "
                                        "colombiano de 10 dígitos."}

    # Solo los ramos del formulario: nada de texto libre del visitante hacia
    # las `dynamic_variables` que recibe el agente de voz.
    interes = req.interes if req.interes in guard.INTERESES else ""
    nombre = (req.nombre or "").strip()[:80]
    device_id = (req.device_id or "").strip()
    ip = request.client.host if request.client else ""

    conn = get_conn()
    try:
        bloqueo = guard.limite_excedido(conn, phone=phone, device_id=device_id, ip=ip)
        if bloqueo:
            return {"ok": False, "mensaje": bloqueo}
        req_id = guard.registrar(
            conn, phone=phone, nombre=nombre or None, interes=interes or None,
            device_id=device_id or None, tenant_id=DEMO_TENANT_ID, consent=True,
            ip=ip or None, user_agent=request.headers.get("user-agent", "")[:300] or None,
            status="solicitada")

        _enviar_ficha_previa(phone, interes, nombre)

        from . import calls
        try:
            resultado = calls.iniciar_llamada(
                phone, DEMO_TENANT_ID,
                dynamic_variables={
                    "nombre_cliente": nombre,
                    "interes_declarado": guard.INTERESES.get(interes, ""),
                    "device_id": device_id,
                    "origen": "landing_callback",
                },
                agent_id=ELEVENLABS_LANDING_AGENT_ID,
            )
        except Exception:
            log.exception("no se pudo iniciar la llamada de prueba desde la landing")
            guard.cerrar(conn, req_id, {"ok": False, "error": "excepción al llamar"})
            return {"ok": False, "mensaje": "No pudimos iniciar la llamada en este momento; "
                                            "intenta de nuevo en unos minutos."}
        guard.cerrar(conn, req_id, resultado)
    finally:
        conn.close()

    if not resultado.get("ok", True):
        # p.ej. fuera de la ventana legal de contacto (Ley 2300/2023)
        return {"ok": False, "mensaje": resultado.get("error") or
                "No pudimos iniciar la llamada en este momento."}

    mensaje = ("Solicitud registrada (modo demo: no se marca de verdad todavía)."
              if resultado.get("demo") else
              "Te estamos llamando — contesta en unos segundos.")
    return {"ok": True, "demo": bool(resultado.get("demo")), "solicitud_id": req_id,
            "mensaje": mensaje}
