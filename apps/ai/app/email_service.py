"""Servicio de email — portado del email_service de Paloma (clients/email_service.py).

Método principal: SMTP (Gmail u otro proveedor). Fallback: Resend.
Conserva las dos lecciones de Paloma:
  1. Circuit breaker de Resend: si el dominio del FROM no está verificado, los
     envíos fallan en bloque; al primer fallo se abre el circuito 1h y los
     envíos devuelven {status: skipped} sin llamar al API.
  2. Throttle local ≤4 req/s para no golpear el rate limit (5/s) de Resend.

Nunca lanza: devuelve {"status": "sent" | "skipped" | "error", ...}.
"""
from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import time
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("seguria.email")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL", "")

_DEFAULT_TEXT_FALLBACK = (
    "Este correo contiene una versión HTML. Si no la ves correctamente, "
    "revisa tu panel de Tequendama Seguros."
)

# ---- Circuit breaker de Resend (estado de módulo, igual que en Paloma) ----
_resend_circuit_open_until: float = 0.0
_resend_circuit_reason: str = ""
_resend_last_send_ts: float = 0.0
_RESEND_DOMAIN_COOLDOWN = 3600  # 1h
_RESEND_RATELIMIT_COOLDOWN = 30  # 30s
_RESEND_MIN_INTERVAL = 0.25  # ≤4 req/s


def _open_circuit(reason: str, cooldown: int) -> None:
    global _resend_circuit_open_until, _resend_circuit_reason
    _resend_circuit_open_until = time.time() + cooldown
    _resend_circuit_reason = reason
    log.warning("Resend circuit OPEN (%ss): %s", cooldown, reason)


def email_configured() -> bool:
    return bool((SMTP_USER and SMTP_PASSWORD) or RESEND_API_KEY)


async def send_email(to: str | list[str], subject: str, html: str,
                     attachments: list[dict] | None = None,
                     text: str | None = None) -> dict:
    """Envía por SMTP (primario) o Resend (fallback)."""
    if SMTP_USER and SMTP_PASSWORD:
        return await _send_via_smtp(to, subject, html, attachments, text)
    if RESEND_API_KEY:
        return await _send_via_resend(to, subject, html, attachments, text)
    log.info("sin proveedor de email configurado; correo a %s no enviado", to)
    return {"status": "skipped", "reason": "no_email_provider"}


async def _send_via_smtp(to, subject, html, attachments=None, text=None) -> dict:
    recipients = to if isinstance(to, list) else [to]
    from_email = SMTP_FROM_EMAIL or SMTP_USER
    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"Tequendama Seguros <{from_email}>"
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject
        body = MIMEMultipart("alternative")
        body.attach(MIMEText(text or _DEFAULT_TEXT_FALLBACK, "plain", "utf-8"))
        body.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(body)
        for att in attachments or []:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(att["content"])
            encoders.encode_base64(part)
            part.add_header("Content-Disposition",
                            f'attachment; filename="{att["filename"]}"')
            msg.attach(part)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _smtp_send_sync,
                                   from_email, recipients, msg.as_string())
        log.info("SMTP enviado a %s", recipients)
        return {"status": "sent"}
    except Exception as exc:
        log.warning("SMTP error a %s: %s", recipients, exc)
        return {"status": "error", "reason": str(exc)}


def _smtp_send_sync(from_email: str, recipients: list[str], msg_string: str) -> None:
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(from_email, recipients, msg_string)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(from_email, recipients, msg_string)


async def _send_via_resend(to, subject, html, attachments=None, text=None) -> dict:
    global _resend_last_send_ts
    if time.time() < _resend_circuit_open_until:
        return {"status": "skipped",
                "reason": f"resend_circuit_open: {_resend_circuit_reason}"}
    delta = time.time() - _resend_last_send_ts
    if delta < _RESEND_MIN_INTERVAL:
        await asyncio.sleep(_RESEND_MIN_INTERVAL - delta)
    try:
        import base64

        import resend
        resend.api_key = RESEND_API_KEY
        recipients = to if isinstance(to, list) else [to]
        params: dict = {
            "from": RESEND_FROM_EMAIL or "Tequendama Seguros <onboarding@resend.dev>",
            "to": recipients,
            "subject": subject,
            "html": html,
        }
        if text:
            params["text"] = text
        if attachments:
            params["attachments"] = [
                {"filename": a["filename"],
                 "content": base64.b64encode(a["content"]).decode("utf-8")}
                for a in attachments
            ]
        result = resend.Emails.send(params)
        _resend_last_send_ts = time.time()
        log.info("Resend enviado a %s: %s", recipients, result.get("id", "ok"))
        return {"id": result.get("id", ""), "status": "sent"}
    except Exception as exc:
        msg = str(exc)
        if "not verified" in msg.lower():
            _open_circuit(f"domain not verified ({msg[:120]})", _RESEND_DOMAIN_COOLDOWN)
            return {"status": "skipped", "reason": "domain_not_verified"}
        if "too many requests" in msg.lower() or "429" in msg:
            _open_circuit("rate limit", _RESEND_RATELIMIT_COOLDOWN)
            return {"status": "skipped", "reason": "rate_limited"}
        log.warning("Resend error a %s: %s", to, exc)
        return {"status": "error", "reason": msg}
