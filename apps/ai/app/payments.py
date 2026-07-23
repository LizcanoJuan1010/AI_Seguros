"""Pagos reales con tarjeta débito/crédito, PSE y Nequi vía Wompi (sandbox).

Patrón "agent toolkit" (Stripe/PayPal/Mercado Pago): las operaciones de pago se
exponen como herramientas de function calling que el asistente configura y
ejecuta en lenguaje natural. La tarjeta NUNCA pasa por el chat ni por este
servidor: el asistente genera un link de pago y el cliente paga en la página
segura de Wompi (el alcance PCI queda del lado de la pasarela).

Flujo: `generar_link_pago` (crea el link y lo registra en el backend) →
`verificar_pago` (webhook del backend → API de Wompi → transaction_id) →
`emitir_poliza` exige estado APPROVED cuando el método no es "simulado" →
`solicitar_aclaracion` (anulación/disputa post-venta, Ley 1480/2011).

Sin `WOMPI_PRIVATE_KEY` todo corre en modo demo (igual que el resto del stack):
el link es simulado y `verificar_pago` aprueba automáticamente.
"""
import logging
import uuid
from typing import Any

import psycopg
import requests

from .config import (BACKEND_URL, WOMPI_BASE_URL, WOMPI_PRIVATE_KEY,
                     WOMPI_REDIRECT_URL)

log = logging.getLogger("seguria.payments")

CHECKOUT_LINK_BASE = "https://checkout.wompi.co/l"
_TIMEOUT = 10

# Estados canónicos (los de Wompi, en mayúsculas) + REFUND_REQUESTED propio.
ESTADO_HUMANO = {
    "PENDING": "pendiente de pago",
    "APPROVED": "aprobado",
    "DECLINED": "rechazado",
    "VOIDED": "anulado (reembolso a la misma tarjeta)",
    "ERROR": "con error en la pasarela",
    "REFUND_REQUESTED": "en aclaración/reembolso",
}


def enabled() -> bool:
    """True si hay llave privada de Wompi (pagos reales contra el sandbox)."""
    return bool(WOMPI_PRIVATE_KEY)


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
        provider TEXT DEFAULT 'wompi',
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
    """Estado del pago según el backend (lo alimenta el webhook de Wompi)."""
    try:
        resp = requests.get(f"{BACKEND_URL}/api/v1/payments/{reference}",
                            timeout=_TIMEOUT, headers={"X-Tenant-Id": tenant_id})
        if resp.status_code == 200:
            return resp.json() or None
    except Exception as exc:
        log.debug("backend de pagos no disponible: %s", exc)
    return None


# ---------- Cliente Wompi ----------

def _headers() -> dict:
    return {"Authorization": f"Bearer {WOMPI_PRIVATE_KEY}"}


def _wompi_create_link(amount_cop: float, concept: str,
                       reference: str) -> tuple[str, str]:
    """Crea el payment link y devuelve (link_id, checkout_url). Lanza si falla."""
    body: dict[str, Any] = {
        "name": concept[:80],
        "description": f"{concept} · Ref {reference}"[:240],
        "single_use": True,
        "collect_shipping": False,
        "currency": "COP",
        "amount_in_cents": int(round(float(amount_cop) * 100)),
        "sku": reference,
    }
    if WOMPI_REDIRECT_URL:
        body["redirect_url"] = WOMPI_REDIRECT_URL
    resp = requests.post(f"{WOMPI_BASE_URL}/payment_links", json=body,
                         timeout=_TIMEOUT, headers=_headers())
    resp.raise_for_status()
    link_id = (resp.json().get("data") or {}).get("id")
    if not link_id:
        raise RuntimeError(f"respuesta de Wompi sin id de link: {resp.text[:200]}")
    return link_id, f"{CHECKOUT_LINK_BASE}/{link_id}"


def _wompi_get_transaction(tx_id: str) -> dict | None:
    try:
        resp = requests.get(f"{WOMPI_BASE_URL}/transactions/{tx_id}",
                            timeout=_TIMEOUT, headers=_headers())
        if resp.status_code == 200:
            return resp.json().get("data") or None
    except Exception as exc:
        log.warning("consulta de transacción %s falló: %s", tx_id, exc)
    return None


def _wompi_find_transaction(link_id: str | None,
                            reference: str | None) -> dict | None:
    """Busca la transacción del link (mejor esfuerzo; el webhook es la fuente
    primaria). Prefiere una APPROVED; si no, la más reciente."""
    for params in ({"payment_link_id": link_id} if link_id else None,
                   {"reference": reference} if reference else None):
        if not params:
            continue
        try:
            resp = requests.get(f"{WOMPI_BASE_URL}/transactions", params=params,
                                timeout=_TIMEOUT, headers=_headers())
            if resp.status_code != 200:
                continue
            txs = resp.json().get("data") or []
            if link_id:  # el filtro puede no aplicar: valida el vínculo
                txs = [t for t in txs
                       if t.get("payment_link_id") in (link_id, None)]
            if txs:
                approved = [t for t in txs if t.get("status") == "APPROVED"]
                return (approved or txs)[0]
        except Exception as exc:
            log.debug("búsqueda de transacciones falló (%s): %s", params, exc)
    return None


def _wompi_void(tx_id: str) -> bool:
    """Anula una transacción aprobada (reembolso a la tarjeta el mismo día)."""
    try:
        resp = requests.post(f"{WOMPI_BASE_URL}/transactions/{tx_id}/void",
                             timeout=_TIMEOUT, headers=_headers())
        return resp.status_code in (200, 201)
    except Exception as exc:
        log.warning("anulación de %s falló: %s", tx_id, exc)
        return False


# ---------- Herramientas del agente ----------

def generar_link_pago(conn: psycopg.Connection, session_key: str,
                      tenant_id: str, args: dict) -> dict:
    """Crea (o reutiliza) el link de pago de la sesión y lo registra en el backend."""
    try:
        monto = round(float(args.get("monto_cop") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0
    if monto <= 0:
        return {"error": "falta el monto en COP; cotiza primero y usa la prima "
                         "mensual de la opción elegida como monto_cop"}
    concept = (args.get("descripcion") or "").strip() or "Primera mensualidad — Seguro SegurIA"

    # Idempotencia: si ya hay un link PENDING por el mismo monto, reutilízalo
    # (el modelo puede reintentar la herramienta en el mismo turno).
    prev = _latest(conn, session_key)
    if prev and prev.get("status") == "PENDING" and \
            abs((prev.get("amount_cop") or 0) - monto) < 1:
        return _payment_out(prev, nota="ya había un link de pago vigente por este "
                                       "monto; entrégaselo de nuevo al cliente")

    reference = f"SEG-{uuid.uuid4().hex[:10].upper()}"
    if enabled():
        try:
            link_id, checkout_url = _wompi_create_link(monto, concept, reference)
        except Exception as exc:
            log.exception("no se pudo crear el link de pago en Wompi")
            return {"error": f"la pasarela no pudo crear el link de pago ({exc}); "
                             "ofrece reintentar o el método 'simulado'"}
        provider = "wompi"
    else:
        link_id, checkout_url, provider = f"demo-{reference}", None, "demo"

    _save(conn, reference, session_key=session_key, link_id=link_id,
          checkout_url=checkout_url, amount_cop=monto, concept=concept,
          status="PENDING", provider=provider)
    _backend_create(tenant_id, {
        "reference": reference, "provider": provider, "linkId": link_id,
        "checkoutUrl": checkout_url, "amountCop": monto, "concept": concept,
        "sessionKey": session_key})

    row = _get(conn, reference) or {}
    nota = None if enabled() else \
        ("modo demo (sin WOMPI_PRIVATE_KEY): no hay página de pago real; "
         "confirma con el cliente y verifica con verificar_pago, que aprobará "
         "el pago simulado")
    return _payment_out(row, nota=nota)


def verificar_pago(conn: psycopg.Connection, session_key: str,
                   tenant_id: str, args: dict) -> dict:
    """Estado del pago: backend (webhook) → API de Wompi → transaction_id directo."""
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
                        "method": "CARD"})
        row = _get(conn, reference) or row
        return _payment_out(row, nota="pago simulado aprobado (modo demo); "
                                      "puedes continuar con emitir_poliza")

    status, tx = row.get("status"), None
    # 1) transaction_id explícito (comprobante del cliente) o ya conocido
    tx_id = (args.get("transaction_id") or "").strip() or row.get("transaction_id")
    if tx_id:
        tx = _wompi_get_transaction(tx_id)
    # 2) backend: el webhook de Wompi lo mantiene al día
    if tx is None:
        backend = _backend_get(tenant_id, reference)
        if backend and str(backend.get("status", "")).upper() not in ("", "PENDING"):
            status = str(backend["status"]).upper()
            tx_id = backend.get("transactionId") or tx_id
    # 3) API de Wompi por link/referencia (cuando el webhook no llega, p.ej. local)
    if tx is None and (status or "PENDING") == "PENDING":
        tx = _wompi_find_transaction(row.get("link_id"), reference)

    if tx:
        status, tx_id = tx.get("status") or status, tx.get("id") or tx_id
    if status and status != row.get("status"):
        _save(conn, reference, status=status, transaction_id=tx_id)
        _backend_patch(tenant_id, reference, {
            "status": status, "transactionId": tx_id,
            "method": (tx or {}).get("payment_method_type")})
        row = _get(conn, reference) or row

    guia = {
        "APPROVED": "pago confirmado: continúa con emitir_poliza pasando "
                    "payment_method='tarjeta' y este payment_reference",
        "PENDING": "aún no registra pago: pide al cliente abrir el link y pagar; "
                   "si ya pagó, pídele el número de transacción del comprobante",
        "DECLINED": "el pago fue rechazado: sugiere reintentar con otro medio",
        "ERROR": "hubo un error en la pasarela: genera un nuevo link",
        "VOIDED": "el pago fue anulado",
    }.get(row.get("status") or "PENDING")
    return _payment_out(row, nota=guia)


def solicitar_aclaracion(conn: psycopg.Connection, session_key: str,
                         tenant_id: str, args: dict) -> dict:
    """Aclaración/disputa post-venta: anula (void) si se puede; si no, la registra."""
    motivo = (args.get("motivo") or "").strip() or "solicitud del cliente"
    reference = (args.get("reference") or "").strip() or None
    row = _get(conn, reference) if reference else _latest(conn, session_key)
    if not row:
        return {"error": "no encuentro pagos en esta sesión para aclarar; "
                         "pide al cliente la referencia SEG-... del cobro"}
    reference = row["reference"]

    if row.get("status") != "APPROVED":
        estado = ESTADO_HUMANO.get(row.get("status") or "PENDING", row.get("status"))
        return {"reference": reference, "status": row.get("status"),
                "mensaje": f"ese pago está {estado}: no hay cobro efectivo que "
                           "aclarar; si el cliente ve un cobro en su extracto, "
                           "pídele el número de transacción del comprobante"}

    if row.get("provider") == "demo":
        nuevo, nota = "REFUND_REQUESTED", ("aclaración registrada (modo demo); el "
                                           "reembolso simulado queda en trámite")
    elif row.get("transaction_id") and _wompi_void(row["transaction_id"]):
        nuevo, nota = "VOIDED", ("transacción anulada: el reembolso llega a la misma "
                                 "tarjeta (mismo día si fue hoy)")
    else:
        nuevo, nota = "REFUND_REQUESTED", (
            "no fue posible anular en línea; la aclaración quedó registrada y el "
            "equipo la gestiona con la pasarela (5 a 15 días hábiles según el emisor)")

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
