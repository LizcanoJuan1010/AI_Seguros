"""KYC (verificación de identidad): documento + prueba de vida + comparación
facial, vía el flujo "Workflow/Session" de Didit (verification.didit.me) — NO
las APIs standalone. Motivo (encontrado probando en vivo esta sesión): el tier
gratis de Didit (500 verificaciones/mes) SOLO aplica al flujo de Workflow; las
APIs standalone (`id-verification`/`passive-liveness`/`face-match` sueltas)
son pago-por-uso desde el primer request. El flujo de Workflow además delega
la captura de cámara/liveness a la página ya probada de Didit, en vez de
nuestro propio JS con `getUserMedia` — menos código, mejor UX.

Flujo (mismo patrón de magic-link que `esign.py`):
  1. WhatsApp/correo entregan un link (`/kyc/{token}`) a NUESTRA página.
  2. Ahí, el cliente da el consentimiento de datos BIOMÉTRICOS — separado del
     habeas data general (Ley 1581/2012 los trata como dato sensible, exige
     autorización propia).
  3. Al aceptar, lo redirigimos a una SESIÓN de Didit (`verify.didit.me/...`):
     ahí hace la captura real (cédula + selfie + prueba de vida) con la
     interfaz de ellos.
  4. Didit redirige de vuelta a `/kyc/{token}/callback`, donde consultamos
     `GET /session/{id}/decision/` y guardamos el veredicto.

Sin `DIDIT_API_KEY` corre en modo demo (mismo criterio que Polar/ElevenLabs en
el resto del stack): aprueba con datos simulados, nunca rompe el flujo.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import requests

from .config import DIDIT_API_KEY, DIDIT_BASE_URL, KYC_LINK_TTL_MINUTES, PUBLIC_BASE_URL

log = logging.getLogger("seguria.kyc")

_TIMEOUT = 30

(REQUESTED, LINK_SENT, CONSENTIDO, REDIRIGIDO, APROBADO, REVISION_MANUAL,
 RECHAZADO, EXPIRADO) = (
    "requested", "link_sent", "consentido", "redirigido",
    "aprobado", "revision_manual", "rechazado", "expirado")
_TERMINAL = (APROBADO, REVISION_MANUAL, RECHAZADO, EXPIRADO)

# Status de Didit (GET /session/{id}/decision/) -> el nuestro. "Not Started"/
# "In Progress" no están acá a propósito: siguen en REDIRIGIDO (no terminal).
_DIDIT_STATUS_MAP = {"Approved": APROBADO, "Declined": RECHAZADO,
                     "In Review": REVISION_MANUAL, "Expired": EXPIRADO}

CONSENTIMIENTO_BIOMETRICO = (
    "Autorización de tratamiento de datos biométricos (Ley 1581 de 2012, "
    "artículos 5 y 6 — datos sensibles): autorizas a Tequendama Seguros a "
    "capturar y procesar tu foto de rostro y la de tu documento de identidad, "
    "ÚNICAMENTE para verificar que eres tú quien contrata la póliza, antes de "
    "emitirla. La captura la realiza nuestro proveedor de verificación (Didit) "
    "en la siguiente pantalla. No estás obligado(a) a autorizarlo salvo que la "
    "ley lo exija para poder emitir tu seguro. Puedes solicitar la eliminación "
    "de estos datos una vez terminada la verificación escribiéndonos.")


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _tables(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS kyc_verifications (
        verification_id TEXT PRIMARY KEY,
        session_key TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        token_hash TEXT UNIQUE,
        status TEXT NOT NULL DEFAULT 'requested',
        consent_biometrico BOOLEAN DEFAULT FALSE,
        consent_biometrico_at TIMESTAMPTZ,
        signer_ip TEXT,
        signer_user_agent TEXT,
        didit_workflow_id TEXT,
        didit_session_id TEXT,
        session_url TEXT,
        full_name TEXT,
        document_number TEXT,
        liveness_status TEXT,
        liveness_score NUMERIC,
        face_match_status TEXT,
        face_match_score NUMERIC,
        decision TEXT,
        decision_reasons JSONB DEFAULT '[]'::jsonb,
        expires_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    # Migra instalaciones con la tabla vieja (versión standalone-API de esta
    # sesión, antes de cambiar al flujo Workflow/session): agrega las
    # columnas nuevas si faltan — CREATE TABLE IF NOT EXISTS no altera una
    # tabla que ya existía con otro shape.
    conn.execute("""ALTER TABLE kyc_verifications
                    ADD COLUMN IF NOT EXISTS didit_workflow_id TEXT,
                    ADD COLUMN IF NOT EXISTS didit_session_id TEXT,
                    ADD COLUMN IF NOT EXISTS session_url TEXT,
                    ADD COLUMN IF NOT EXISTS liveness_status TEXT,
                    ADD COLUMN IF NOT EXISTS liveness_score NUMERIC,
                    ADD COLUMN IF NOT EXISTS face_match_status TEXT,
                    ADD COLUMN IF NOT EXISTS face_match_score NUMERIC""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_kyc_session
                    ON kyc_verifications (session_key, created_at)""")
    # Workflow de Didit: se crea UNA vez y se reusa para todas las sesiones
    # (no hay que recrearlo por cliente). Ver `_ensure_workflow`.
    conn.execute("""CREATE TABLE IF NOT EXISTS kyc_workflow (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        workflow_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def enabled() -> bool:
    return bool(DIDIT_API_KEY)


def _headers() -> dict:
    return {"x-api-key": DIDIT_API_KEY}


def _is_expired(row: dict) -> bool:
    exp = row.get("expires_at")
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > exp


def get_verification(conn: psycopg.Connection, verification_id: str) -> dict | None:
    _tables(conn)
    row = conn.execute("SELECT * FROM kyc_verifications WHERE verification_id=%s",
                       (verification_id,)).fetchone()
    return dict(row) if row else None


def get_by_token(conn: psycopg.Connection, token: str) -> dict | None:
    _tables(conn)
    row = conn.execute("SELECT * FROM kyc_verifications WHERE token_hash=%s",
                       (_token_hash(token),)).fetchone()
    return dict(row) if row else None


def latest_for_session(conn: psycopg.Connection, session_key: str) -> dict | None:
    """Última verificación de la sesión, con el estado YA refrescado contra
    Didit si estaba pendiente (mismo criterio activo que `verificar_pago`:
    nunca confíes en un estado guardado que podría estar desactualizado)."""
    _tables(conn)
    row = conn.execute(
        """SELECT * FROM kyc_verifications WHERE session_key=%s
           ORDER BY created_at DESC LIMIT 1""", (session_key,)).fetchone()
    if not row:
        return None
    row = dict(row)
    if row["status"] == REDIRIGIDO:
        row = refresh_decision(conn, row)
    return row


def latest_pending(conn: psycopg.Connection, session_key: str) -> dict | None:
    _tables(conn)
    row = conn.execute(
        """SELECT * FROM kyc_verifications WHERE session_key=%s
           AND status NOT IN ('aprobado','rechazado','expirado')
           ORDER BY created_at DESC LIMIT 1""", (session_key,)).fetchone()
    return dict(row) if row else None


def is_verified(conn: psycopg.Connection, session_key: str) -> bool:
    row = latest_for_session(conn, session_key)
    return bool(row and row["status"] == APROBADO)


def _deliver(link_url: str, *, phone: str | None, email: str | None) -> dict:
    sent_via = []
    texto = ("Tequendama Seguros: para activar tu póliza necesitamos "
             f"verificar tu identidad. Abre este link desde tu celular y ten "
             f"a la mano tu cédula:\n{link_url}\n\nToma solo un par de minutos.")
    if phone:
        try:
            from . import whatsapp_gateway
            if whatsapp_gateway.enviar_whatsapp(phone, texto):
                sent_via.append("whatsapp")
        except Exception:
            log.warning("no se pudo enviar el link de KYC por WhatsApp", exc_info=True)
    if email:
        try:
            import asyncio

            from .email_service import send_email
            html = (f"<p>Para activar tu póliza necesitamos verificar tu identidad. "
                    f"Abre este link desde tu celular:</p><p><a href='{link_url}'>{link_url}</a></p>")
            result = asyncio.run(send_email(email, "Verifica tu identidad — Tequendama Seguros",
                                            html, text=texto))
            if result.get("status") == "sent":
                sent_via.append("email")
        except Exception:
            log.warning("no se pudo enviar el link de KYC por correo", exc_info=True)
    return {"sent_via": sent_via}


def request_verification(conn: psycopg.Connection, session_key: str, tenant_id: str, *,
                         phone: str | None = None, email: str | None = None) -> dict:
    """Crea la verificación, arma el link a NUESTRA página (`/kyc/{token}`,
    consentimiento) y lo entrega. La sesión de Didit se crea después, recién
    cuando el cliente consienta (ver `create_didit_session`) — así no se gasta
    una sesión de Didit por cada link que se manda y nunca se abre."""
    _tables(conn)
    verification_id = f"kyc_{uuid.uuid4().hex[:12]}"
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=KYC_LINK_TTL_MINUTES)
    link_url = f"{PUBLIC_BASE_URL}/kyc/{token}"
    if not PUBLIC_BASE_URL:
        log.warning("PUBLIC_BASE_URL vacío: el link de KYC (%s) no será absoluto", link_url)

    conn.execute(
        """INSERT INTO kyc_verifications
               (verification_id, session_key, tenant_id, token_hash, status, expires_at)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (verification_id, session_key, tenant_id, _token_hash(token), REQUESTED, expires_at))
    delivery = _deliver(link_url, phone=phone, email=email)
    conn.execute("UPDATE kyc_verifications SET status=%s, updated_at=now() WHERE verification_id=%s",
                (LINK_SENT, verification_id))
    conn.commit()
    return {"verification_id": verification_id, "sent_via": delivery["sent_via"],
           "link_url": link_url if not delivery["sent_via"] else None}


def record_consent(conn: psycopg.Connection, token: str, *, ip: str | None,
                   user_agent: str | None) -> dict | None:
    _tables(conn)
    row = get_by_token(conn, token)
    if row is None:
        return None
    if row["status"] in _TERMINAL:
        return row
    if _is_expired(row):
        conn.execute("UPDATE kyc_verifications SET status=%s, updated_at=now() "
                    "WHERE verification_id=%s", (EXPIRADO, row["verification_id"]))
        conn.commit()
        return get_verification(conn, row["verification_id"])
    conn.execute(
        """UPDATE kyc_verifications SET status=%s, consent_biometrico=TRUE,
               consent_biometrico_at=now(), signer_ip=%s, signer_user_agent=%s, updated_at=now()
           WHERE verification_id=%s""",
        (CONSENTIDO, ip, user_agent, row["verification_id"]))
    conn.commit()
    return get_verification(conn, row["verification_id"])


# ---------- Workflow/Session de Didit ----------

def _ensure_workflow(conn: psycopg.Connection) -> str:
    """El workflow_id se crea UNA sola vez (reusable para todas las sesiones)
    y se guarda en `kyc_workflow`. En modo demo devuelve un id fijo."""
    row = conn.execute(
        "SELECT workflow_id FROM kyc_workflow ORDER BY id DESC LIMIT 1").fetchone()
    if row:
        return row["workflow_id"]
    if not enabled():
        workflow_id = "demo-workflow"
    else:
        # Schema real de /v3/workflows/ (verificado contra la API — la doc
        # pública de terceros describe una versión distinta/vieja): `features`
        # es una lista de objetos `{"feature": "<ENUM>"}`. OCR = lectura del
        # documento (no existe un "ID_VERIFICATION" en el enum real).
        resp = requests.post(
            f"{DIDIT_BASE_URL}/v3/workflows/", headers=_headers(),
            json={"workflow_label": "Tequendama KYC",
                 "features": [{"feature": "OCR"}, {"feature": "LIVENESS"},
                              {"feature": "FACE_MATCH"}]},
            timeout=_TIMEOUT)
        resp.raise_for_status()
        workflow_id = resp.json()["uuid"]
        log.info("workflow de Didit creado: %s", workflow_id)
    conn.execute("INSERT INTO kyc_workflow (workflow_id) VALUES (%s)", (workflow_id,))
    conn.commit()
    return workflow_id


def _demo_session(conn: psycopg.Connection, row: dict) -> dict:
    """Sin DIDIT_API_KEY no hay página de Didit real a la que redirigir —
    aprueba directo con datos simulados, como el resto del stack en demo."""
    conn.execute(
        """UPDATE kyc_verifications SET status=%s, decision=%s,
               full_name=COALESCE(full_name, 'Cliente Demo'),
               document_number=COALESCE(document_number, '100000000'), updated_at=now()
           WHERE verification_id=%s""",
        (APROBADO, APROBADO, row["verification_id"]))
    conn.commit()
    return {"ok": True, "demo": True, "session_url": None,
           "mensaje": "Modo demo (sin DIDIT_API_KEY): verificación aprobada automáticamente."}


def create_didit_session(conn: psycopg.Connection, token: str) -> dict:
    """Tras el consentimiento: crea (o reusa) la sesión de Didit y devuelve la
    URL a la que el navegador debe redirigir para la captura real."""
    _tables(conn)
    row = get_by_token(conn, token)
    if row is None:
        return {"error": "link inválido o desconocido"}
    if row["status"] in _TERMINAL:
        return {"error": f"esta verificación ya está {row['status']}"}
    if not row.get("consent_biometrico"):
        return {"error": "falta el consentimiento de datos biométricos"}
    if row.get("session_url") and row["status"] == REDIRIGIDO:
        return {"ok": True, "session_url": row["session_url"]}  # idempotente

    if not enabled():
        return _demo_session(conn, row)

    try:
        workflow_id = _ensure_workflow(conn)
        callback = f"{PUBLIC_BASE_URL}/kyc/{token}/callback"
        resp = requests.post(
            f"{DIDIT_BASE_URL}/v3/session/", headers=_headers(),
            json={"workflow_id": workflow_id, "vendor_data": row["verification_id"],
                 "callback": callback, "language": "es"}, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.warning("no se pudo crear la sesión de Didit: %s", exc)
        return {"error": "no se pudo iniciar la verificación; intenta de nuevo en un momento"}

    conn.execute(
        """UPDATE kyc_verifications SET status=%s, didit_workflow_id=%s,
               didit_session_id=%s, session_url=%s, updated_at=now()
           WHERE verification_id=%s""",
        (REDIRIGIDO, workflow_id, data.get("session_id"), data.get("url"),
         row["verification_id"]))
    conn.commit()
    return {"ok": True, "session_url": data.get("url")}


def refresh_decision(conn: psycopg.Connection, row: dict) -> dict:
    """Consulta `GET /session/{id}/decision/` y actualiza nuestro registro si
    Didit ya tiene un veredicto terminal. Idempotente y silencioso ante fallas
    de red — nunca rompe al llamador (mismo criterio que `payments.verificar_pago`)."""
    if row["status"] != REDIRIGIDO or not row.get("didit_session_id") or not enabled():
        return row
    try:
        resp = requests.get(f"{DIDIT_BASE_URL}/v3/session/{row['didit_session_id']}/decision/",
                            headers=_headers(), timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log.info("no se pudo consultar la decisión de Didit todavía: %s", exc)
        return row

    mapped = _DIDIT_STATUS_MAP.get(data.get("status"))
    if not mapped:
        return row  # "Not Started"/"In Progress": el cliente sigue en la captura

    # Didit cruza documento<->selfie SOLO (misma sesión, un id_verification y un
    # face_match); no expone un id de referencia explícito entre ambos porque no
    # hace falta — nosotros solo guardamos los resultados para auditoría/revisión
    # manual, la decisión ya viene combinada en `status`.
    idv = (data.get("id_verifications") or [{}])[0] if data.get("id_verifications") else {}
    live = (data.get("liveness_checks") or [{}])[0] if data.get("liveness_checks") else {}
    fm = (data.get("face_matches") or [{}])[0] if data.get("face_matches") else {}
    full_name = idv.get("full_name") or f"{idv.get('first_name', '')} {idv.get('last_name', '')}".strip()

    conn.execute(
        """UPDATE kyc_verifications SET status=%s, decision=%s,
               full_name=COALESCE(NULLIF(%s,''), full_name),
               document_number=COALESCE(%s, document_number),
               liveness_status=%s, liveness_score=%s,
               face_match_status=%s, face_match_score=%s, updated_at=now()
           WHERE verification_id=%s""",
        (mapped, mapped, full_name, idv.get("document_number"),
         live.get("status"), live.get("score"), fm.get("status"), fm.get("score"),
         row["verification_id"]))
    conn.commit()
    if mapped == REVISION_MANUAL:
        reasons = [f"documento: {idv.get('status')}", f"liveness: {live.get('score')} ({live.get('status')})",
                  f"face_match: {fm.get('score')} ({fm.get('status')})"]
        _notify_manual_review(row["tenant_id"], row["verification_id"],
                              full_name or row.get("full_name"), reasons)
    return get_verification(conn, row["verification_id"])


def _notify_manual_review(tenant_id: str, verification_id: str, full_name: str | None,
                          reasons: list[str]) -> None:
    """Alerta al gerente (best-effort) — mismo patrón que
    agent_core._notify_referral / claims_ai._notify_fraud."""
    try:
        import re

        from .config import BACKEND_URL
        msg = (f"KYC en revisión manual ({verification_id}): {full_name or 'cliente'}. "
              f"Motivos: {'; '.join(reasons)}")
        payload = {"message": msg[:900], "severity": "alta"}
        if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
                   tenant_id or "", re.I):
            payload["teamId"] = tenant_id
        requests.post(f"{BACKEND_URL}/api/v1/alerts", json=payload, timeout=5,
                     headers={"X-Tenant-Id": tenant_id})
    except Exception:
        log.debug("no se pudo crear la alerta de KYC en revisión", exc_info=True)


def public_view(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        "verification_id": row["verification_id"],
        "status": row["status"],
        "decision": row.get("decision"),
        "decision_reasons": row.get("decision_reasons") if row.get("decision") != APROBADO else [],
        "consent_biometrico": row.get("consent_biometrico"),
        "session_url": row.get("session_url") if row["status"] == REDIRIGIDO else None,
        "expires_at": row.get("expires_at"),
    }
