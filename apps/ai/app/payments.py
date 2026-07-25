"""Pagos reales con tarjeta débito/crédito vía Polar (polar.sh, sandbox).

Patrón "agent toolkit" (Stripe/PayPal/Mercado Pago): las operaciones de pago se
exponen como herramientas de function calling que el asistente configura y
ejecuta en lenguaje natural. La tarjeta NUNCA pasa por el chat ni por este
servidor: el asistente genera un checkout y el cliente paga en la página segura
de Polar (el alcance PCI queda del lado de la pasarela). El cobro se hace en
COP (Polar soporta `cop` como presentment currency).

Flujo: `generar_link_pago` crea un producto one-time con la prima y su checkout
session (metadata.reference = SEG-...) → `verificar_pago` (webhook del backend
→ estado del checkout → orden) → `emitir_poliza` exige estado APPROVED cuando
el método no es "simulado" → `solicitar_aclaracion` (refund total / disputa
post-venta, Ley 1480/2011).

Sin `POLAR_ACCESS_TOKEN` todo corre en modo demo (igual que el resto del stack):
el link es simulado y `verificar_pago` aprueba automáticamente.
"""
import logging
import uuid
from typing import Any

import psycopg
import requests

from .config import (BACKEND_URL, POLAR_ACCESS_TOKEN, POLAR_BASE_URL,
                     POLAR_SUCCESS_URL)

log = logging.getLogger("seguria.payments")

_TIMEOUT = 15

# Estados canónicos del pago en TODO el stack (tabla payments del backend,
# frames SSE y respuestas al LLM) + mapeo desde los estados de Polar.
ESTADO_HUMANO = {
    "PENDING": "pendiente de pago",
    "APPROVED": "aprobado",
    "DECLINED": "rechazado o vencido",
    "VOIDED": "reembolsado",
    "ERROR": "con error en la pasarela",
    "REFUND_REQUESTED": "en aclaración/reembolso",
}

# Checkout de Polar: open|confirmed → pendiente; succeeded → pagado;
# expired|failed → rechazado/vencido.
_CHECKOUT_STATUS_MAP = {
    "open": "PENDING",
    "confirmed": "PENDING",
    "succeeded": "APPROVED",
    "expired": "DECLINED",
    "failed": "DECLINED",
}

# Motivo libre del cliente → enum RefundReason de Polar.
_REFUND_REASONS = (
    ("duplicad", "duplicate"),
    ("fraud", "fraudulent"),
    ("no funciona", "service_disruption"),
    ("no recib", "service_disruption"),
)


def enabled() -> bool:
    """True si hay token de Polar (pagos reales contra el sandbox)."""
    return bool(POLAR_ACCESS_TOKEN)


# ---------- Store de pagos de la sesión (esquema `seguria`) ----------

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


# ---------- Backend NestJS (sistema de registro de pagos, best-effort) ----------

def _backend_create(tenant_id: str, payment: dict) -> None:
    try:
        requests.post(f"{BACKEND_URL}/api/v1/payments", json=payment,
                      timeout=_TIMEOUT, headers={"X-Tenant-Id": tenant_id}
                      ).raise_for_status()
    except Exception as exc:  # el registro central no debe bloquear la venta
        log.warning("no se pudo registrar el pago en el backend: %s", exc)


def _backend_patch(tenant_id: str, reference: str, fields: dict) -> None:
    try:
        requests.patch(f"{BACKEND_URL}/api/v1/payments/{reference}", json=fields,
                       timeout=_TIMEOUT, headers={"X-Tenant-Id": tenant_id}
                       ).raise_for_status()
    except Exception as exc:
        log.warning("no se pudo actualizar el pago en el backend: %s", exc)


def _backend_get(tenant_id: str, reference: str) -> dict | None:
    """Estado del pago según el backend (lo alimenta el webhook de Polar)."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/payments/{reference}",
                            timeout=_TIMEOUT, headers={"X-Tenant-Id": tenant_id})
        if resp.status_code == 200:
            return resp.json() or None
    except Exception as exc:
        log.debug("backend de pagos no disponible: %s", exc)
    return None


# ---------- Cliente Polar (API REST, sandbox por defecto) ----------

def _headers() -> dict:
    return {"Authorization": f"Bearer {POLAR_ACCESS_TOKEN}"}


def _polar_create_checkout(amount_cop: float, concept: str,
                           reference: str) -> tuple[str, str]:
    """Producto one-time (prima en COP) + checkout session. → (checkout_id, url).

    Polar no permite montos libres en productos de precio fijo, así que cada
    cobro crea su propio producto con la prima exacta (visibility=hidden para
    no ensuciar el catálogo). El checkout lleva metadata.reference para que el
    webhook `order.paid` pueda correlacionar el pago."""
    name = (concept or "Prima seguro Tequendama").strip()[:64]
    if len(name) < 3:  # Polar exige nombre de 3-64 caracteres
        name = f"Pago {reference}"
    prod = requests.post(f"{POLAR_BASE_URL}/products/", timeout=_TIMEOUT,
                         headers=_headers(), json={
                             "name": name,
                             "recurring_interval": None,
                             "visibility": "hidden",
                             "metadata": {"reference": reference},
                             "prices": [{"amount_type": "fixed",
                                         "price_currency": "cop",
                                         "price_amount": int(round(float(amount_cop) * 100))}],
                         })
    prod.raise_for_status()
    product_id = prod.json().get("id")
    if not product_id:
        raise RuntimeError(f"respuesta de Polar sin id de producto: {prod.text[:200]}")

    body: dict[str, Any] = {"products": [product_id],
                            "metadata": {"reference": reference}}
    if POLAR_SUCCESS_URL:
        body["success_url"] = POLAR_SUCCESS_URL
    resp = requests.post(f"{POLAR_BASE_URL}/checkouts/", json=body,
                         timeout=_TIMEOUT, headers=_headers())
    resp.raise_for_status()
    data = resp.json()
    checkout_id, url = data.get("id"), data.get("url")
    if not checkout_id or not url:
        raise RuntimeError(f"respuesta de Polar sin checkout: {resp.text[:200]}")
    return checkout_id, url


def _polar_get_checkout_status(checkout_id: str) -> str | None:
    """Estado canónico del checkout (PENDING/APPROVED/DECLINED) o None si falla."""
    try:
        resp = requests.get(f"{POLAR_BASE_URL}/checkouts/{checkout_id}",
                            timeout=_TIMEOUT, headers=_headers())
        if resp.status_code == 200:
            return _CHECKOUT_STATUS_MAP.get(resp.json().get("status") or "")
    except Exception as exc:
        log.warning("consulta del checkout %s falló: %s", checkout_id, exc)
    return None


def _polar_find_order(checkout_id: str | None = None,
                      order_id: str | None = None) -> dict | None:
    """Orden pagada de un checkout (o por id directo del comprobante)."""
    try:
        if order_id:
            resp = requests.get(f"{POLAR_BASE_URL}/orders/{order_id}",
                                timeout=_TIMEOUT, headers=_headers())
            return resp.json() if resp.status_code == 200 else None
        if checkout_id:
            resp = requests.get(f"{POLAR_BASE_URL}/orders/",
                                params={"checkout_id": checkout_id, "limit": 1},
                                timeout=_TIMEOUT, headers=_headers())
            if resp.status_code == 200:
                items = resp.json().get("items") or []
                return items[0] if items else None
    except Exception as exc:
        log.debug("búsqueda de orden falló (checkout=%s): %s", checkout_id, exc)
    return None


def _polar_refund(order: dict, motivo: str) -> bool:
    """Refund TOTAL de la orden (refundable_amount). True si Polar lo aceptó."""
    amount = order.get("refundable_amount") or order.get("total_amount") or 0
    if amount <= 0:
        return False
    norm = motivo.lower()
    reason = next((r for k, r in _REFUND_REASONS if k in norm), "customer_request")
    try:
        resp = requests.post(f"{POLAR_BASE_URL}/refunds/", timeout=_TIMEOUT,
                             headers=_headers(), json={
                                 "order_id": order["id"], "reason": reason,
                                 "amount": amount,
                                 "metadata": {"motivo": motivo[:500]}})
        return resp.status_code in (200, 201)
    except Exception as exc:
        log.warning("refund de la orden %s falló: %s", order.get("id"), exc)
        return False


# ---------- Herramientas del agente ----------

def generar_link_pago(conn: psycopg.Connection, session_key: str,
                      tenant_id: str, args: dict) -> dict:
    """Crea (o reutiliza) el checkout de pago de la sesión y lo registra en el backend."""
    try:
        monto = round(float(args.get("monto_cop") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0
    if monto <= 0:
        return {"error": "falta el monto en COP; cotiza primero y usa la prima "
                         "mensual de la opción elegida como monto_cop"}
    concept = (args.get("descripcion") or "").strip() or "Primera mensualidad — Seguro Tequendama"

    # Idempotencia: si ya hay un checkout PENDING por el mismo monto, reutilízalo
    # (el modelo puede reintentar la herramienta en el mismo turno).
    prev = _latest(conn, session_key)
    if prev and prev.get("status") == "PENDING" and \
            abs((prev.get("amount_cop") or 0) - monto) < 1:
        return _payment_out(prev, nota="ya había un link de pago vigente por este "
                                       "monto; entrégaselo de nuevo al cliente")

    reference = f"SEG-{uuid.uuid4().hex[:10].upper()}"
    if enabled():
        try:
            checkout_id, checkout_url = _polar_create_checkout(monto, concept, reference)
        except Exception as exc:
            log.exception("no se pudo crear el checkout en Polar")
            return {"error": f"la pasarela no pudo crear el link de pago ({exc}); "
                             "ofrece reintentar o el método 'simulado'"}
        provider = "polar"
    else:
        checkout_id, checkout_url, provider = f"demo-{reference}", None, "demo"

    _save(conn, reference, session_key=session_key, link_id=checkout_id,
          checkout_url=checkout_url, amount_cop=monto, concept=concept,
          status="PENDING", provider=provider)
    _backend_create(tenant_id, {
        "reference": reference, "provider": provider, "linkId": checkout_id,
        "checkoutUrl": checkout_url, "amountCop": monto, "concept": concept,
        "sessionKey": session_key})

    row = _get(conn, reference) or {}
    nota = None if enabled() else \
        ("modo demo (sin POLAR_ACCESS_TOKEN): no hay página de pago real; "
         "confirma con el cliente y verifica con verificar_pago, que aprobará "
         "el pago simulado")
    return _payment_out(row, nota=nota)


def verificar_pago(conn: psycopg.Connection, session_key: str,
                   tenant_id: str, args: dict) -> dict:
    """Estado del pago: backend (webhook) → checkout de Polar → orden directa."""
    reference = (args.get("reference") or "").strip() or None
    row = _get(conn, reference) if reference else _latest(conn, session_key)
    if not row:
        return {"error": "no hay ningún pago iniciado en esta sesión; "
                         "genera primero el link con generar_link_pago"}
    reference = row["reference"]

    if row.get("provider") == "demo":
        _save(conn, reference, status="APPROVED",
              transaction_id=f"demo-tx-{reference}")
        _backend_patch(tenant_id, reference,
                       {"status": "APPROVED", "transactionId": f"demo-tx-{reference}",
                        "method": "card"})
        row = _get(conn, reference) or row
        return _payment_out(row, nota="pago simulado aprobado (modo demo); "
                                      "puedes continuar con emitir_poliza")

    status, tx_id = row.get("status"), row.get("transaction_id")
    # 1) id de orden explícito (del comprobante que el cliente ve en Polar)
    order_arg = (args.get("transaction_id") or "").strip() or None
    order = _polar_find_order(order_id=order_arg) if order_arg else None
    # 2) backend: el webhook order.paid de Polar lo mantiene al día
    if order is None:
        backend = _backend_get(tenant_id, reference)
        if backend and str(backend.get("status", "")).upper() not in ("", "PENDING"):
            status = str(backend["status"]).upper()
            tx_id = backend.get("transactionId") or tx_id
    # 3) API de Polar: estado del checkout (cuando el webhook no llega, p.ej. local)
    if order is None and (status or "PENDING") == "PENDING":
        polled = _polar_get_checkout_status(row.get("link_id"))
        if polled:
            status = polled
        if status == "APPROVED":
            order = _polar_find_order(checkout_id=row.get("link_id"))

    if order and order.get("paid"):
        status, tx_id = "APPROVED", order.get("id") or tx_id
    if status and status != row.get("status"):
        _save(conn, reference, status=status, transaction_id=tx_id)
        _backend_patch(tenant_id, reference,
                       {"status": status, "transactionId": tx_id, "method": "card"})
        row = _get(conn, reference) or row

    guia = {
        "APPROVED": "pago confirmado: continúa con emitir_poliza pasando "
                    "payment_method='tarjeta' y este payment_reference",
        "PENDING": "aún no registra pago: pide al cliente abrir el link y pagar; "
                   "si ya pagó, pídele el ID de la orden del comprobante",
        "DECLINED": "el pago fue rechazado o el link venció: genera un nuevo link",
        "ERROR": "hubo un error en la pasarela: genera un nuevo link",
        "VOIDED": "el pago fue reembolsado",
    }.get(row.get("status") or "PENDING")
    return _payment_out(row, nota=guia)


def solicitar_aclaracion(conn: psycopg.Connection, session_key: str,
                         tenant_id: str, args: dict) -> dict:
    """Aclaración/disputa post-venta: refund total si se puede; si no, la registra."""
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
        nuevo, nota = "REFUND_REQUESTED", ("aclaración registrada (modo demo); el "
                                           "reembolso simulado queda en trámite")
    else:
        order = _polar_find_order(checkout_id=row.get("link_id"),
                                  order_id=row.get("transaction_id"))
        if order and _polar_refund(order, motivo):
            nuevo, nota = "VOIDED", ("reembolso total emitido: el dinero vuelve al "
                                     "mismo medio de pago (5 a 10 días hábiles "
                                     "según el emisor de la tarjeta)")
        else:
            nuevo, nota = "REFUND_REQUESTED", (
                "no fue posible reembolsar en línea; la aclaración quedó registrada "
                "y el equipo la gestiona con la pasarela (5 a 15 días hábiles)")

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
