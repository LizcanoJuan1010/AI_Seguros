"""Reclamos (FNOL: primer aviso de siniestro) por chat/WhatsApp.

Cierra el ciclo venta → póliza → SINIESTRO. El triage es determinista y
auditable (severidad, banderas de fraude explicables); el LLM solo conversa.
El reclamo vive en el dominio Prisma (`public.claims`, vía
`POST {BACKEND_URL}/api/v1/claims`) para que el gerente lo vea en su panel;
si el backend no responde, se degrada a un número provisional (patrón
`emitir_poliza`). Las consultas de estado van directas por la BD compartida.
"""
import json
import logging
import re
from datetime import date, datetime
from typing import Any

import psycopg

from .config import BACKEND_URL, DATA_DIR

log = logging.getLogger("seguria.claims")

# Banderas de fraude: umbrales explícitos (nunca decide el LLM).
EARLY_CLAIM_DAYS = 30          # siniestro a <30 días de emitida la póliza
HIGH_AMOUNT_RATIO = 5.0        # monto estimado > 5x la prima anual
FRAUD_ALERT_THRESHOLD = 0.5    # score desde el cual se alerta al gerente

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)

_REQUISITOS: dict | None = None


def _requisitos() -> dict:
    global _REQUISITOS
    if _REQUISITOS is None:
        try:
            _REQUISITOS = json.loads(
                (DATA_DIR / "requisitos_siniestros.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("sin requisitos_siniestros.json; se usa lista genérica")
            _REQUISITOS = {}
    return _REQUISITOS


def documentos_para(tipo: str) -> list[str]:
    """Documentos de soporte requeridos para un tipo de siniestro."""
    req = _requisitos()
    por_tipo = req.get("por_tipo") or {}
    entry = por_tipo.get((tipo or "").strip().lower()) or req.get("default") or {}
    return entry.get("documentos") or [
        "Documento de identidad", "Soportes del evento", "Facturas de la pérdida"]


def _parse_fecha(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _find_policy(conn: psycopg.Connection, policy_number: str) -> dict | None:
    """Póliza del dominio (public.*) con titular y tipo; None si no existe."""
    try:
        row = conn.execute(
            """SELECT p.id::text policy_id, p.policy_number, p.status::text status,
                      p.start_date, p.end_date, p.monthly_premium_cop::float prima_cop,
                      p.customer_id::text customer_id, c.full_name,
                      pr.insurance_type::text tipo
               FROM public.policies p
               JOIN public.customers c ON c.id = p.customer_id
               JOIN public.quotes q ON q.id = p.quote_id
               JOIN public.products pr ON pr.id = q.product_id
               WHERE p.policy_number ILIKE %s""", (policy_number,)).fetchone()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        return None


def _fraud_signals(conn: psycopg.Connection, policy: dict, *,
                   monto_cop: float, fecha_incidente: date | None) -> tuple[float, list[str]]:
    """Score 0-1 + banderas explicables. Heurísticas deterministas."""
    score, flags = 0.0, []
    hoy = date.today()
    inc = fecha_incidente or hoy

    if inc > hoy:
        score += 0.5
        flags.append("fecha_futura: el incidente reportado aún no ocurre")
    start = policy.get("start_date")
    if start and (inc - start).days <= EARLY_CLAIM_DAYS:
        score += 0.4
        flags.append(f"siniestro_temprano: a {(inc - start).days} días de emitida la póliza")
    prima = policy.get("prima_cop") or 0
    if monto_cop and prima and monto_cop > prima * 12 * HIGH_AMOUNT_RATIO:
        score += 0.3
        flags.append("monto_alto_vs_prima: estimado supera 5x la prima anual")
    try:
        n = conn.execute(
            "SELECT COUNT(*) n FROM public.claims WHERE customer_id = %s::uuid",
            (policy["customer_id"],)).fetchone()["n"]
        if n >= 1:
            score += 0.2
            flags.append(f"reclamos_previos: el cliente ya tiene {n} reclamo(s)")
    except Exception:
        conn.rollback()
    return min(round(score, 2), 0.95), flags


def _notify_fraud(tenant_id: str, claim_number: str, policy: dict,
                  score: float, flags: list[str]) -> None:
    """Alerta al gerente cuando el score de fraude supera el umbral (best-effort)."""
    try:
        import requests
        msg = (f"Reclamo {claim_number} ({policy.get('full_name')}, póliza "
               f"{policy.get('policy_number')}): score de fraude {score:.2f}. "
               f"Señales: {'; '.join(flags)}")
        payload = {"message": msg[:900], "severity": "alta"}
        if _UUID4_RE.match(tenant_id or ""):
            payload["teamId"] = tenant_id
        requests.post(f"{BACKEND_URL}/api/v1/alerts", json=payload, timeout=5,
                      headers={"X-Tenant-Id": tenant_id})
    except Exception:
        log.debug("no se pudo crear la alerta de fraude", exc_info=True)


def reportar_siniestro(conn: psycopg.Connection, tenant_id: str, args: dict) -> dict:
    """FNOL: valida la póliza, hace triage y registra el reclamo en el dominio."""
    policy_number = str(args.get("policy_number") or "").strip()
    descripcion = str(args.get("descripcion") or "").strip()
    if not policy_number:
        return {"error": "falta policy_number; pídele al cliente su número de póliza (POL-...)"}
    if not descripcion:
        return {"error": "falta la descripción de lo que pasó; pídesela al cliente"}

    policy = _find_policy(conn, policy_number)
    if not policy:
        return {"error": f"no encontré la póliza {policy_number}; verifica el número"}
    if policy["status"] != "vigente":
        return {"error": f"la póliza {policy['policy_number']} está en estado "
                         f"'{policy['status']}'; solo pólizas vigentes pueden reclamar",
                "estado_poliza": policy["status"]}

    fecha_incidente = _parse_fecha(args.get("fecha_incidente"))
    try:
        monto = round(float(args.get("monto_estimado_cop") or 0), 2)
    except (TypeError, ValueError):
        monto = 0.0
    file_ids = [str(f) for f in (args.get("file_ids") or []) if f]

    score, flags = _fraud_signals(conn, policy, monto_cop=monto,
                                  fecha_incidente=fecha_incidente)
    docs = documentos_para(policy["tipo"])
    resumen = (f"{policy['tipo'].capitalize()}: {descripcion[:200]}"
               + (f" · Estimado {monto:,.0f} COP" if monto else ""))

    payload = {
        "policyId": policy["policy_id"],
        "customerId": policy["customer_id"],
        "insuranceType": policy["tipo"].upper(),
        "description": descripcion[:1000],
        **({"incidentDate": fecha_incidente.isoformat()} if fecha_incidente else {}),
        **({"amountEstimateCop": monto} if monto else {}),
        "fraudScore": score,
        "fraudFlags": flags,
        "documents": file_ids,
        "aiSummary": resumen,
    }

    degraded = False
    try:
        import requests
        resp = requests.post(f"{BACKEND_URL}/api/v1/claims", json=payload, timeout=8,
                             headers={"X-Tenant-Id": tenant_id})
        resp.raise_for_status()
        claim = resp.json() or {}
        claim_number = claim.get("claimNumber")
        status = claim.get("status") or "REPORTADO"
    except Exception as exc:
        log.warning("backend de reclamos no disponible (%s); registro provisional", exc)
        degraded = True
        now = datetime.utcnow()
        claim_number = f"CLM-LOCAL-{now.strftime('%Y')}-{now.strftime('%m%d%H%M%S')}"
        status = "REPORTADO"

    if score >= FRAUD_ALERT_THRESHOLD and not degraded:
        _notify_fraud(tenant_id, claim_number, policy, score, flags)

    return {
        "claim_number": claim_number,
        "status": status,
        "tipo": policy["tipo"],
        "poliza": policy["policy_number"],
        "titular": policy["full_name"],
        "documentos_requeridos": docs,
        "documentos_adjuntos": len(file_ids),
        "fraud_score": score,
        "fraud_flags": flags,
        "degraded": degraded,
        "mensaje": ("Reclamo registrado. Confírmale al cliente el número, dile qué documentos "
                    "faltan (puede enviarlos por el chat) y que le avisaremos en cada cambio "
                    "de estado. Las banderas de fraude son INTERNAS: nunca las menciones al "
                    "cliente; el equipo las revisa."),
    }


def estado_siniestro(conn: psycopg.Connection, args: dict) -> dict:
    """Consulta el estado de un reclamo por número (BD compartida)."""
    claim_number = str(args.get("claim_number") or "").strip()
    if not claim_number:
        return {"error": "falta claim_number (CLM-...)"}
    try:
        row = conn.execute(
            """SELECT cl.claim_number, cl.status::text status,
                      cl.insurance_type::text tipo, cl.description,
                      cl.created_at, cl.updated_at, p.policy_number
               FROM public.claims cl
               LEFT JOIN public.policies p ON p.id = cl.policy_id
               WHERE cl.claim_number ILIKE %s""", (claim_number,)).fetchone()
    except Exception:
        conn.rollback()
        row = None
    if not row:
        return {"error": f"no encontré el reclamo {claim_number}"}
    return {
        "claim_number": row["claim_number"],
        "status": row["status"].upper(),
        "tipo": row["tipo"],
        "poliza": row["policy_number"],
        "reportado_el": str(row["created_at"])[:16],
        "ultima_actualizacion": str(row["updated_at"])[:16],
        "mensaje": ("Explica el estado en lenguaje simple: reportado = recibido; "
                    "en_revision = un analista lo evalúa; docs_pendientes = faltan "
                    "documentos; aprobado/pagado = buena noticia; rechazado = explica "
                    "con empatía y ofrece escalar a un asesor."),
    }
