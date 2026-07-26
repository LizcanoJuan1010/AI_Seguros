"""Firma electrónica in-house tipo clickwrap (Ley 527 de 1999, Colombia:
validez de mensajes de datos y firmas electrónicas) — adaptado de
`tools/esign.py` de Diache (mismo patrón: link único + clic = evidencia de
no repudio + auditoría encadenada por hash), simplificado para Tequendama:
sin proveedores SMS externos (Aircall/Vapi) — el link se entrega por los
canales que YA existen en este proyecto (WhatsApp + correo).

Flujo:
  1. `request_signature` guarda el texto EXACTO mostrado (hash sha256 —
     asociación firma<->documento), crea un token opaco (solo su hash se
     persiste) y arma `PUBLIC_BASE_URL/sign/{token}`. Lo entrega por
     WhatsApp/correo (best-effort, nunca rompe si un canal falla).
  2. El cliente abre el link (`GET /sign/{token}` en main.py) y hace clic en
     "Acepto" — `POST /sign/{token}/accept` captura IP/User-Agent como
     evidencia y llama `sign()`.
  3. `is_signed()` es el gate que usa `agent_core._emitir_poliza` — sin firma
     no hay emisión, mismo criterio que consentimiento/pago/underwriting.

Nunca lanza hacia el llamador: errores de entrega o de BD degradan a
{"error": ...} o a no auditar, sin tumbar el turno del agente.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from .config import ESIGN_LINK_TTL_MINUTES, PUBLIC_BASE_URL

log = logging.getLogger("seguria.esign")

REQUESTED, LINK_SENT, SIGNED, DECLINED, EXPIRED = (
    "requested", "link_sent", "signed", "declined", "expired")
_TERMINAL = (SIGNED, DECLINED, EXPIRED)

TERMINOS_AUTORIZACION_POLIZA = (
    "Autorización de emisión de póliza (Ley 527 de 1999): al hacer clic en "
    "\"Acepto\" autorizas a Tequendama Seguros (Colsubsidio) a emitir la "
    "póliza en las condiciones y prima que se te presentaron en el chat. Esta "
    "firma electrónica tiene la misma validez legal que una firma manuscrita. "
    "Cuentas con derecho de retracto durante los 5 días hábiles siguientes "
    "(Ley 1480/2011). Puedes solicitar copia de este documento en cualquier "
    "momento escribiéndonos.")


def terms_hash(body: str) -> str:
    return hashlib.sha256((body or "").encode()).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _tables(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS esign_signatures (
        signature_id TEXT PRIMARY KEY,
        session_key TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        purpose TEXT NOT NULL,
        terms_text TEXT NOT NULL,
        terms_hash TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'requested'
            CHECK (status IN ('requested','link_sent','signed','declined','expired')),
        token_hash TEXT UNIQUE,
        signer_phone TEXT,
        signer_email TEXT,
        signer_ip TEXT,
        signer_user_agent TEXT,
        evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
        expires_at TIMESTAMPTZ,
        signed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_esign_session
                    ON esign_signatures (session_key, created_at)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS esign_audit (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        ts TIMESTAMPTZ NOT NULL DEFAULT now(),
        session_key TEXT,
        event_type TEXT NOT NULL,
        subject TEXT,
        payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        prev_hash TEXT,
        hash TEXT NOT NULL)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_esign_audit_subject
                    ON esign_audit (subject, id)""")


def _canonical(prev_hash: str | None, ts_iso: str, event_type: str,
              subject: str | None, payload: dict) -> str:
    body = (f"{prev_hash or ''}|{ts_iso}|{event_type}|{subject or ''}|"
            f"{json.dumps(payload, sort_keys=True, default=str)}")
    return hashlib.sha256(body.encode()).hexdigest()


def _audit(conn: psycopg.Connection, *, session_key: str, event_type: str,
          subject: str, payload: dict | None = None) -> None:
    """Evento append-only encadenado por hash (no repudio). Nunca rompe el
    flujo si falla — es evidencia, no lógica de negocio."""
    try:
        payload = payload or {}
        ts = datetime.now(timezone.utc)
        ts_iso = ts.isoformat()
        conn.execute("SELECT pg_advisory_xact_lock(hashtext('seguria_esign_audit'))")
        row = conn.execute("SELECT hash FROM esign_audit ORDER BY id DESC LIMIT 1").fetchone()
        prev_hash = row["hash"] if row else None
        digest = _canonical(prev_hash, ts_iso, event_type, subject, payload)
        conn.execute(
            """INSERT INTO esign_audit (ts, session_key, event_type, subject, payload,
                                        prev_hash, hash)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (ts, session_key, event_type, subject, json.dumps(payload, default=str),
             prev_hash, digest))
    except Exception:
        log.warning("no se pudo auditar el evento de firma (%s/%s)", event_type, subject,
                   exc_info=True)


def _deliver(sign_url: str, *, phone: str | None, email: str | None) -> dict:
    """Entrega el link por los canales ya existentes del proyecto. Best-effort:
    un canal caído no bloquea al otro ni el registro de la firma."""
    sent_via = []
    texto = ("Tequendama Seguros: para activar tu póliza necesitamos tu "
             f"autorización. Es un solo clic, no toma ni un minuto:\n{sign_url}\n\n"
             "El link vence en unas horas por seguridad.")
    if phone:
        try:
            from . import whatsapp_gateway
            if whatsapp_gateway.enviar_whatsapp(phone, texto):
                sent_via.append("whatsapp")
        except Exception:
            log.warning("no se pudo enviar el link de firma por WhatsApp", exc_info=True)
    if email:
        try:
            import asyncio

            from .email_service import send_email
            html = (f"<p>Para activar tu póliza necesitamos tu autorización. "
                    f"Es un solo clic:</p><p><a href='{sign_url}'>{sign_url}</a></p>"
                    f"<p>El link vence en unas horas por seguridad.</p>")
            result = asyncio.run(send_email(email, "Autoriza tu póliza — Tequendama Seguros",
                                            html, text=texto))
            if result.get("status") == "sent":
                sent_via.append("email")
            else:
                log.warning("correo de firma a %s no salió: %s (%s)", email,
                            result.get("status"), result.get("reason"))
        except Exception:
            log.warning("no se pudo enviar el link de firma por correo", exc_info=True)
    return {"sent_via": sent_via}


def request_signature(conn: psycopg.Connection, session_key: str, tenant_id: str, *,
                      purpose: str = "autorizacion_poliza",
                      terms_text: str = TERMINOS_AUTORIZACION_POLIZA,
                      phone: str | None = None, email: str | None = None) -> dict:
    """Crea la solicitud de firma, arma el link y lo entrega. Devuelve un
    payload seguro para el LLM (nunca expone el token, solo la URL ya armada
    una vez, igual que Diache: el token no se puede reconstruir del hash)."""
    _tables(conn)
    signature_id = f"sig_{uuid.uuid4().hex[:12]}"
    token = secrets.token_urlsafe(32)
    thash = terms_hash(terms_text)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ESIGN_LINK_TTL_MINUTES)
    sign_url = f"{PUBLIC_BASE_URL}/sign/{token}"
    if not PUBLIC_BASE_URL:
        log.warning("PUBLIC_BASE_URL vacío: el link de firma (%s) no será un "
                    "enlace absoluto — no funcionará si se abre fuera de este host", sign_url)

    conn.execute(
        """INSERT INTO esign_signatures
               (signature_id, session_key, tenant_id, purpose, terms_text, terms_hash,
                status, token_hash, signer_phone, signer_email, expires_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (signature_id, session_key, tenant_id, purpose, terms_text, thash,
         REQUESTED, _token_hash(token), phone, email, expires_at))
    _audit(conn, session_key=session_key, event_type="terms_presented",
          subject=signature_id, payload={"purpose": purpose, "terms_hash": thash})
    _audit(conn, session_key=session_key, event_type="signature_requested",
          subject=signature_id, payload={"purpose": purpose})

    delivery = _deliver(sign_url, phone=phone, email=email)
    conn.execute("UPDATE esign_signatures SET status=%s, updated_at=now() WHERE signature_id=%s",
                (LINK_SENT, signature_id))
    _audit(conn, session_key=session_key, event_type="link_sent",
          subject=signature_id, payload=delivery)
    conn.commit()

    row = get_signature(conn, signature_id)
    return public_view(row, sign_url=sign_url)


def get_signature(conn: psycopg.Connection, signature_id: str) -> dict | None:
    _tables(conn)
    row = conn.execute("SELECT * FROM esign_signatures WHERE signature_id=%s",
                       (signature_id,)).fetchone()
    return dict(row) if row else None


def get_by_token(conn: psycopg.Connection, token: str) -> dict | None:
    _tables(conn)
    row = conn.execute("SELECT * FROM esign_signatures WHERE token_hash=%s",
                       (_token_hash(token),)).fetchone()
    return dict(row) if row else None


def _is_expired(row: dict) -> bool:
    exp = row.get("expires_at")
    if exp is None:
        return False
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > exp


def sign(conn: psycopg.Connection, token: str, *, agree: bool,
        ip: str | None = None, user_agent: str | None = None) -> dict | None:
    """Registra la decisión del clic (idempotente). Evidencia de no repudio:
    IP + User-Agent + hash exacto de los términos mostrados + timestamp."""
    _tables(conn)
    row = get_by_token(conn, token)
    if row is None:
        return None
    if row["status"] in _TERMINAL:
        return row  # replay idempotente

    if _is_expired(row):
        conn.execute("UPDATE esign_signatures SET status=%s, updated_at=now() "
                    "WHERE signature_id=%s", (EXPIRED, row["signature_id"]))
        _audit(conn, session_key=row["session_key"], event_type="signature_expired",
              subject=row["signature_id"])
        conn.commit()
        return get_signature(conn, row["signature_id"])

    if not agree:
        conn.execute("UPDATE esign_signatures SET status=%s, updated_at=now() "
                    "WHERE signature_id=%s", (DECLINED, row["signature_id"]))
        _audit(conn, session_key=row["session_key"], event_type="signature_declined",
              subject=row["signature_id"])
        conn.commit()
        return get_signature(conn, row["signature_id"])

    signed_at = datetime.now(timezone.utc)
    evidence = {"ip": ip, "user_agent": user_agent, "terms_hash": row["terms_hash"],
               "agreed_at": signed_at.isoformat(), "method": "clickwrap"}
    conn.execute(
        """UPDATE esign_signatures SET status=%s, signed_at=%s, signer_ip=%s,
               signer_user_agent=%s, evidence=%s, updated_at=now()
           WHERE signature_id=%s AND status NOT IN ('signed','declined','expired')""",
        (SIGNED, signed_at, ip, user_agent, json.dumps(evidence), row["signature_id"]))
    _audit(conn, session_key=row["session_key"], event_type="signature_signed",
          subject=row["signature_id"], payload={"evidence": evidence})
    conn.commit()
    return get_signature(conn, row["signature_id"])


def is_signed(conn: psycopg.Connection, session_key: str, purpose: str) -> bool:
    """Gate para `emitir_poliza`: True solo si la firma más reciente de ese
    propósito quedó en estado 'signed'."""
    _tables(conn)
    row = conn.execute(
        """SELECT status FROM esign_signatures WHERE session_key=%s AND purpose=%s
           ORDER BY created_at DESC LIMIT 1""", (session_key, purpose)).fetchone()
    return bool(row and row["status"] == SIGNED)


def latest_pending(conn: psycopg.Connection, session_key: str, purpose: str) -> dict | None:
    """Última firma no resuelta de ese propósito (para no crear un link nuevo
    si ya hay uno vigente sin abrir)."""
    _tables(conn)
    row = conn.execute(
        """SELECT * FROM esign_signatures WHERE session_key=%s AND purpose=%s
           AND status IN ('requested','link_sent') ORDER BY created_at DESC LIMIT 1""",
        (session_key, purpose)).fetchone()
    return dict(row) if row else None


def public_view(row: dict | None, *, sign_url: str | None = None) -> dict | None:
    """Vista segura para el LLM/cliente: el token nunca se expone salvo en la
    creación (y solo porque el llamador ya lo tiene a mano ahí mismo)."""
    if row is None:
        return None
    return {
        "signature_id": row["signature_id"],
        "purpose": row["purpose"],
        "status": row["status"],
        "sign_url": sign_url if row["status"] in (REQUESTED, LINK_SENT) else None,
        "signed_at": row.get("signed_at"),
        "expires_at": row.get("expires_at"),
    }
