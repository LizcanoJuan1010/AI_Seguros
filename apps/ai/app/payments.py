"""Pagos vía Nest (Polar sandbox o demo).

Patrón "agent toolkit": las operaciones de pago se exponen como herramientas
de function calling. La tarjeta NUNCA pasa por el chat ni por este servidor:
Nest crea el checkout Polar y el cliente paga en la página segura de la
pasarela (PCI del lado de Polar).

Flujo: `generar_link_pago` → Nest `POST /api/v1/payments/checkout` →
`verificar_pago` → Nest GET (ledger webhook-driven; demo APPROVE vía PATCH) →
`emitir_poliza` exige APPROVED → `solicitar_aclaracion` registra disputa en Nest.

Este módulo es un cliente HTTP delgado: NO llama a Polar ni requiere
`POLAR_ACCESS_TOKEN`. El token vive solo en Nest.
"""
import logging
import uuid
from typing import Any

import psycopg
import requests

from .config import BACKEND_URL

log = logging.getLogger("seguria.payments")

_TIMEOUT = 15

# Estados canónicos del pago en TODO el stack (tabla payments del backend,
# frames SSE y respuestas al LLM).
ESTADO_HUMANO = {
    "PENDING": "pendiente de pago",
    "APPROVED": "aprobado",
    "DECLINED": "rechazado o vencido",
    "VOIDED": "reembolsado",
    "ERROR": "con error en la pasarela",
    "REFUND_REQUESTED": "en aclaración/reembolso",
}


# ---------- Store de pagos de la sesión (esquema `seguria`, espejo cache) ----------

def _table(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS payment_session (
        reference TEXT PRIMARY KEY,
        session_key TEXT,
        link_id TEXT,
        checkout_url TEXT,
        amount_cop DOUBLE PRECISION,
        concept TEXT,
        status TEXT DEFAULT 'PENDING',
        transaction_id TEXT,
        provider TEXT DEFAULT 'polar',
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_payment_session_key
                    ON payment_session (session_key)""")


def _get(conn: psycopg.Connection, reference: str) -> dict | None:
    _table(conn)
    row = conn.execute("SELECT * FROM payment_session WHERE reference=%s",
                       (reference,)).fetchone()
    return dict(row) if row else None


def _latest(conn: psycopg.Connection, session_key: str) -> dict | None:
    _table(conn)
    row = conn.execute(
        "SELECT * FROM payment_session WHERE session_key=%s "
        "ORDER BY created_at DESC LIMIT 1", (session_key,)).fetchone()
    return dict(row) if row else None


def _save(conn: psycopg.Connection, reference: str, **fields) -> None:
    _table(conn)
    cols = ("session_key", "link_id", "checkout_url", "amount_cop", "concept",
            "status", "transaction_id", "provider")
    current = _get(conn, reference) or {}
    merged = {**current, **{k: v for k, v in fields.items() if v is not None}}
    conn.execute(
        f"""INSERT INTO payment_session (reference, {', '.join(cols)})
            VALUES (%s{',%s' * len(cols)})
            ON CONFLICT (reference) DO UPDATE SET
            {', '.join(f'{c}=excluded.{c}' for c in cols)}, updated_at=now()""",
        (reference, *[merged.get(c) for c in cols]))
    conn.commit()


def approved_for_session(conn: psycopg.Connection, session_key: str,
                         reference: str | None = None) -> dict | None:
    """Pago APPROVED de la sesión (o el de `reference`), para gatear la emisión."""
    row = _get(conn, reference) if reference else _latest(conn, session_key)
    return row if row and row.get("status") == "APPROVED" else None


# ---------- Cliente Nest (única fuente de verdad Polar / demo) ----------

def _headers(tenant_id: str) -> dict[str, str]:
    return {"X-Tenant-Id": tenant_id, "Content-Type": "application/json"}


def _backend_checkout(tenant_id: str, amount_cop: float, concept: str,
                      session_key: str) -> dict[str, Any]:
    """POST /api/v1/payments/checkout → Nest crea Polar o demo."""
    resp = requests.post(
        f"{BACKEND_URL}/api/v1/payments/checkout",
        json={
            "amountCop": amount_cop,
            "concept": concept,
            "sessionKey": session_key,
        },
        timeout=_TIMEOUT,
        headers=_headers(tenant_id),
    )
    resp.raise_for_status()
    return resp.json() or {}


def _backend_create(tenant_id: str, payment: dict) -> None:
    """POST /api/v1/payments (alta genérica, sin checkout Polar) — la usa
    `activar_recaudo_nomina`, que no pasa por `_backend_checkout` porque no
    hay checkout externo que crear (la inscripción ES el pago). Nest siempre
    crea en PENDING (ver CreatePaymentDto); el caller debe confirmar el
    estado real con un `_backend_patch` después, igual que hace el resto del
    módulo (best-effort: un fallo acá no debe bloquear la venta)."""
    try:
        requests.post(f"{BACKEND_URL}/api/v1/payments", json=payment,
                     timeout=_TIMEOUT, headers=_headers(tenant_id)).raise_for_status()
    except Exception as exc:
        log.warning("no se pudo registrar el pago en el backend: %s", exc)


def _backend_patch(tenant_id: str, reference: str, fields: dict) -> None:
    try:
        requests.patch(
            f"{BACKEND_URL}/api/v1/payments/{reference}",
            json=fields,
            timeout=_TIMEOUT,
            headers=_headers(tenant_id),
        ).raise_for_status()
    except Exception as exc:
        log.warning("no se pudo actualizar el pago en el backend: %s", exc)


def _backend_get(tenant_id: str, reference: str) -> dict | None:
    """Estado del pago según Nest (ledger alimentado por webhook Polar)."""
    try:
        resp = requests.get(
            f"{BACKEND_URL}/api/v1/payments/{reference}",
            timeout=_TIMEOUT,
            headers=_headers(tenant_id),
        )
        if resp.status_code == 200:
            return resp.json() or None
    except Exception as exc:
        log.debug("backend de pagos no disponible: %s", exc)
    return None


def _nest_to_row(data: dict, session_key: str) -> dict:
    """Normaliza respuesta camelCase de Nest a filas snake_case locales."""
    return {
        "reference": data.get("reference"),
        "link_id": data.get("linkId") or data.get("link_id"),
        "checkout_url": data.get("checkoutUrl") if "checkoutUrl" in data
        else data.get("checkout_url"),
        "amount_cop": data.get("amountCop", data.get("amount_cop")),
        "concept": data.get("concept"),
        "status": str(data.get("status") or "PENDING").upper(),
        "transaction_id": data.get("transactionId") or data.get("transaction_id"),
        "provider": data.get("provider") or "polar",
        "session_key": session_key,
    }


# ---------- Herramientas del agente ----------

def generar_link_pago(conn: psycopg.Connection, session_key: str,
                      tenant_id: str, args: dict) -> dict:
    """Crea (o reutiliza) el checkout vía Nest y lo espeja en payment_session."""
    try:
        monto = round(float(args.get("monto_cop") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0
    if monto <= 0:
        return {"error": "falta el monto en COP; cotiza primero y usa la prima "
                         "mensual de la opción elegida como monto_cop"}
    concept = (args.get("descripcion") or "").strip() or \
        "Primera mensualidad — Seguro Tequendama"

    # Idempotencia: reutilizar PENDING del mismo monto.
    prev = _latest(conn, session_key)
    if prev and prev.get("status") == "PENDING" and \
            abs((prev.get("amount_cop") or 0) - monto) < 1:
        return _payment_out(prev, nota="ya había un link de pago vigente por este "
                                       "monto; entrégaselo de nuevo al cliente")

    try:
        nest = _backend_checkout(tenant_id, monto, concept, session_key)
    except Exception as exc:
        log.exception("Nest no pudo crear el checkout")
        return {"error": f"la pasarela no pudo crear el link de pago ({exc}); "
                         "ofrece reintentar o el método 'simulado'"}

    reference = nest.get("reference")
    if not reference:
        return {"error": "el backend no devolvió reference del checkout"}

    row_data = _nest_to_row(nest, session_key)
    _save(conn, reference, session_key=session_key,
          link_id=row_data.get("link_id"),
          checkout_url=row_data.get("checkout_url"),
          amount_cop=monto, concept=concept, status="PENDING",
          provider=row_data.get("provider"))

    row = _get(conn, reference) or row_data
    demo = bool(nest.get("demo") or row.get("provider") == "demo")
    nota = None if not demo else (
        "modo demo (Nest sin POLAR_ACCESS_TOKEN): no hay página de pago real; "
        "confirma con el cliente y verifica con verificar_pago, que aprobará "
        "el pago simulado vía Nest")
    return _payment_out(row, nota=nota)


def activar_recaudo_nomina(conn: psycopg.Connection, session_key: str,
                          tenant_id: str, args: dict) -> dict:
    """Recaudo vía descuento de nómina — ventaja de persistencia estructural
    de Colsubsidio (relación con el empleador del afiliado) frente a la
    tarjeta, cuyo rechazo destruye carteras completas (ver
    Nota_estrategica_Seguros_Colsubsidio.pdf §3). A diferencia de
    `generar_link_pago`, no hay checkout externo que abrir: la inscripción ES
    el compromiso de pago — se marca APPROVED de inmediato para no bloquear
    la emisión, igual que el modo demo, pero registrado como su propio
    proveedor ("nomina") para no mezclarlo en reportes con pagos simulados/
    de prueba."""
    try:
        monto = round(float(args.get("monto_cop") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0
    if monto <= 0:
        return {"error": "falta el monto en COP; cotiza primero y usa la prima "
                         "mensual de la opción elegida como monto_cop"}
    concept = (args.get("descripcion") or "").strip() or "Primera mensualidad — Seguro Tequendama"

    reference = f"SEG-{uuid.uuid4().hex[:10].upper()}"
    tx_id = f"nomina-{reference}"
    # Localmente (payment_session) ya nace APPROVED — es nuestra caché, y la
    # inscripción es el compromiso. En Nest, CreatePaymentDto solo permite
    # PENDING al crear: crea y confirma con un patch aparte (mismo patrón que
    # el resto del módulo usa para el flujo demo).
    _save(conn, reference, session_key=session_key, link_id=None, checkout_url=None,
         amount_cop=monto, concept=concept, status="APPROVED",
         transaction_id=tx_id, provider="nomina")
    _backend_create(tenant_id, {
        "reference": reference, "provider": "nomina", "amountCop": monto,
        "concept": concept, "sessionKey": session_key})
    _backend_patch(tenant_id, reference,
                   {"status": "APPROVED", "transactionId": tx_id, "method": "nomina"})

    row = _get(conn, reference) or {}
    return _payment_out(row, nota="inscrito al descuento por nómina; el primer "
                                  "descuento se aplica en el próximo ciclo de pago. "
                                  "Puedes continuar con emitir_poliza "
                                  "(payment_method='nomina').")


def verificar_pago(conn: psycopg.Connection, session_key: str,
                   tenant_id: str, args: dict) -> dict:
    """Estado del pago: solo Nest GET (+ PATCH demo APPROVE). Sin Polar HTTP."""
    reference = (args.get("reference") or "").strip() or None
    row = _get(conn, reference) if reference else _latest(conn, session_key)
    if not row:
        return {"error": "no hay ningún pago iniciado en esta sesión; "
                         "genera primero el link con generar_link_pago"}
    reference = row["reference"]

    backend = _backend_get(tenant_id, reference)
    provider = (backend or {}).get("provider") or row.get("provider")
    status = str((backend or {}).get("status") or row.get("status") or "PENDING").upper()
    tx_id = (backend or {}).get("transactionId") or row.get("transaction_id")

    # Demo: Nest-owned auto-APPROVE vía PATCH (AI no escribe verdad sola).
    if provider == "demo" and status == "PENDING":
        tx_id = tx_id or f"demo-tx-{reference}"
        _backend_patch(tenant_id, reference, {
            "status": "APPROVED",
            "transactionId": tx_id,
            "method": "card",
        })
        status = "APPROVED"

    if status != row.get("status") or tx_id != row.get("transaction_id"):
        _save(conn, reference, status=status, transaction_id=tx_id,
              provider=provider)
        row = _get(conn, reference) or row
    else:
        row = {**row, "status": status, "transaction_id": tx_id,
               "provider": provider}

    if provider == "demo" and status == "APPROVED":
        return _payment_out(row, nota="pago simulado aprobado (modo demo); "
                                      "puedes continuar con emitir_poliza")

    guia = {
        "APPROVED": "pago confirmado: continúa con emitir_poliza pasando "
                    "payment_method='tarjeta' y este payment_reference",
        "PENDING": "aún no registra pago: pide al cliente abrir el botón/CTA "
                   "en pantalla (o el link de WhatsApp) y pagar; no leas la URL "
                   "completa en voz",
        "DECLINED": "el pago fue rechazado o el link venció: genera un nuevo link",
        "ERROR": "hubo un error en la pasarela: genera un nuevo link",
        "VOIDED": "el pago fue reembolsado",
    }.get(row.get("status") or "PENDING")
    return _payment_out(row, nota=guia)


def solicitar_aclaracion(conn: psycopg.Connection, session_key: str,
                         tenant_id: str, args: dict) -> dict:
    """Aclaración/disputa post-venta: registra en Nest (sin Polar HTTP desde AI)."""
    motivo = (args.get("motivo") or "").strip() or "solicitud del cliente"
    reference = (args.get("reference") or "").strip() or None
    row = _get(conn, reference) if reference else _latest(conn, session_key)
    if not row:
        return {"error": "no encuentro pagos en esta sesión para aclarar; "
                         "pide al cliente la referencia SEG-... del cobro"}
    reference = row["reference"]

    if row.get("status") not in ("APPROVED", "REFUND_REQUESTED"):
        estado = ESTADO_HUMANO.get(row.get("status") or "PENDING", row.get("status"))
        return {"reference": reference, "status": row.get("status"),
                "mensaje": f"ese pago está {estado}: no hay cobro efectivo que "
                           "aclarar; si el cliente ve un cobro en su extracto, "
                           "pídele el ID de la orden del comprobante"}

    if row.get("provider") == "demo":
        nuevo, nota = "REFUND_REQUESTED", (
            "aclaración registrada (modo demo); el reembolso simulado queda "
            "en trámite")
    else:
        nuevo, nota = "REFUND_REQUESTED", (
            "la aclaración quedó registrada en el backend; el equipo la "
            "gestiona con la pasarela (5 a 15 días hábiles)")

    _save(conn, reference, status=nuevo)
    _backend_patch(tenant_id, reference,
                   {"status": nuevo, "disputeReason": f"{motivo}"[:500]})
    row = _get(conn, reference) or row
    return _payment_out(row, nota=nota, motivo=motivo)


def _payment_out(row: dict, nota: str | None = None,
                 motivo: str | None = None) -> dict:
    """Payload estructurado y estable de un pago para el LLM y los frames SSE."""
    status = row.get("status") or "PENDING"
    out = {
        "reference": row.get("reference"),
        "checkout_url": row.get("checkout_url"),
        "amount_cop": row.get("amount_cop"),
        "concept": row.get("concept"),
        "status": status,
        "estado": ESTADO_HUMANO.get(status, status),
        "provider": row.get("provider"),
        "transaction_id": row.get("transaction_id"),
        "demo": row.get("provider") == "demo",
    }
    if nota:
        out["nota"] = nota
    if motivo:
        out["motivo"] = motivo
    return out
