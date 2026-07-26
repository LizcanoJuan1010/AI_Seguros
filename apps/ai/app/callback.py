"""Capa anti-abuso de la puerta anónima de la landing ("déjanos tu número").

El endpoint vive en `landing_callback.py`; esto es solo lo que hace falta para
poder exponerlo sin login: validar el número, dejar rastro auditable del
consentimiento y frenar el uso abusivo. Se separó del handler porque son dos
responsabilidades con ciclos de vida distintos — el handler cambia cuando
cambia el guion de la llamada; esto cambia cuando cambia la política de abuso.

Por qué hace falta: `/api/calls/outbound` exige X-Service-Key porque lo dispara
un gerente desde el CRM. Esta puerta la abre cualquier visitante, y cada
solicitud gasta minutos de telefonía a un número que el visitante escribe —
sin tope, sirve para hostigar a un tercero con nuestra cuenta pagando.

Lo que NO cubre — verificación OTP. Hoy nada prueba que el número sea de quien
lo escribe; lo único que lo contiene es que la cuenta de Twilio en trial solo
marca a números verificados a mano en su consola. Al salir de trial hay que
exigir un código por SMS/WhatsApp antes de llamar (el gancho natural va entre
`limite_excedido` y el disparo de la llamada en `landing_callback`).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import psycopg

from .config import (CALLBACK_MAX_POR_DISPOSITIVO, CALLBACK_MAX_POR_IP,
                     CALLBACK_MAX_POR_TELEFONO, DEFAULT_COUNTRY_CODE)

log = logging.getLogger("seguria.callback")

# Ramos que ofrece el formulario (mismos que ProductCards.tsx). Se valida contra
# esta lista cerrada para que no entre texto libre del visitante a las
# `dynamic_variables` que recibe el agente de voz.
INTERESES = {
    "vida": "Seguro de Vida",
    "auto": "Seguro de Auto",
    "salud": "Seguro de Salud",
    "hogar": "Seguro de Hogar",
    "otro": "Todavía no lo tengo claro",
}

_SOLO_DIGITOS = re.compile(r"\D+")


def normalizar_telefono(raw: str, *, cc: str = "") -> str | None:
    """"300 123 4567" / "3001234567" / "+57 300 123 4567" -> "+573001234567".

    Devuelve None si no parece marcable. Acepta E.164 de otro país tal cual
    (por si la landing algún día sirve fuera de Colombia); para un número local
    asume `cc` (default DEFAULT_COUNTRY_CODE)."""
    s = (raw or "").strip()
    if not s:
        return None
    tiene_mas = s.startswith("+")
    digitos = _SOLO_DIGITOS.sub("", s)
    if not digitos:
        return None

    cc = (cc or DEFAULT_COUNTRY_CODE).lstrip("+")
    if tiene_mas:
        return f"+{digitos}" if 8 <= len(digitos) <= 15 else None
    if digitos.startswith(cc) and len(digitos) > 10:
        return f"+{digitos}"
    if len(digitos) == 10:
        return f"+{cc}{digitos}"
    return None


def es_celular_colombiano(phone: str) -> bool:
    """True si es un celular colombiano (+57 3XXXXXXXXX). El agente de voz solo
    tiene sentido en móvil: a un fijo de oficina no le sirve el flujo, y el
    formulario ya muestra el "+57" fijo al lado del campo."""
    return bool(re.fullmatch(r"\+573\d{9}", phone or ""))


def tabla(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS callback_request (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        phone TEXT NOT NULL,
        nombre TEXT,
        interes TEXT,
        device_id TEXT,
        tenant_id TEXT,
        consent BOOLEAN NOT NULL DEFAULT FALSE,
        consent_at TIMESTAMPTZ,
        ip TEXT,
        user_agent TEXT,
        status TEXT NOT NULL DEFAULT 'solicitada',
        conversation_id TEXT,
        call_sid TEXT,
        error TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_callback_phone
                    ON callback_request (phone, created_at DESC)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_callback_device
                    ON callback_request (device_id, created_at DESC)""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_callback_ip
                    ON callback_request (ip, created_at DESC)""")


def _cuenta_ultima_hora(conn: psycopg.Connection, campo: str, valor: str) -> int:
    """Solicitudes de la última hora para ese teléfono/dispositivo/IP. `campo`
    NO viene del usuario: son literales del código (ver `_LIMITES`)."""
    desde = datetime.now(timezone.utc) - timedelta(hours=1)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM callback_request WHERE {campo}=%s AND created_at >= %s",
        (valor, desde)).fetchone()
    return int(row["n"]) if row else 0


def _limites() -> list[tuple[str, int, str]]:
    """(columna, tope/hora, mensaje). Se reporta el primero que topa."""
    return [
        ("phone", CALLBACK_MAX_POR_TELEFONO,
         "Ya solicitaste varias llamadas a este número en la última hora. "
         "Espera un momento y vuelve a intentarlo."),
        ("device_id", CALLBACK_MAX_POR_DISPOSITIVO,
         "Demasiadas solicitudes desde este navegador en la última hora."),
        ("ip", CALLBACK_MAX_POR_IP,
         "Demasiadas solicitudes desde esta conexión en la última hora."),
    ]


def limite_excedido(conn: psycopg.Connection, *, phone: str, device_id: str = "",
                    ip: str = "") -> str | None:
    """Mensaje para el visitante si topó algún límite, o None si puede seguir.
    Fail-open: si la BD no responde, deja pasar — una landing caída por no
    poder contar solicitudes es peor que una llamada de más."""
    try:
        tabla(conn)
        for campo, tope, mensaje in _limites():
            valor = {"phone": phone, "device_id": device_id, "ip": ip}[campo]
            if valor and _cuenta_ultima_hora(conn, campo, valor) >= tope:
                log.info("callback bloqueado por límite de %s (%s)", campo, valor)
                return mensaje
    except Exception:
        conn.rollback()
        log.warning("no se pudieron evaluar los límites de callback", exc_info=True)
    return None


def registrar(conn: psycopg.Connection, **campos) -> int | None:
    """Deja la solicitud en `callback_request` — es el rastro auditable del
    consentimiento (Ley 1581/2012 exige poder demostrar cuándo y desde dónde se
    autorizó el contacto) y a la vez el contador de los límites de arriba.
    Nunca lanza: si la BD falla, la llamada igual se dispara."""
    try:
        tabla(conn)
        row = conn.execute(
            """INSERT INTO callback_request
               (phone, nombre, interes, device_id, tenant_id, consent, consent_at,
                ip, user_agent, status)
               VALUES (%(phone)s, %(nombre)s, %(interes)s, %(device_id)s, %(tenant_id)s,
                       %(consent)s, now(), %(ip)s, %(user_agent)s, %(status)s)
               RETURNING id""", campos).fetchone()
        conn.commit()
        return int(row["id"]) if row else None
    except Exception:
        conn.rollback()
        log.warning("no se pudo registrar la solicitud de llamada", exc_info=True)
        return None


def cerrar(conn: psycopg.Connection, req_id: int | None, resultado: dict) -> None:
    """Anota en la solicitud cómo terminó el disparo de la llamada."""
    if not req_id:
        return
    try:
        conn.execute(
            """UPDATE callback_request
               SET status=%s, conversation_id=%s, call_sid=%s, error=%s
               WHERE id=%s""",
            ("demo" if resultado.get("demo") else
             ("llamando" if resultado.get("ok") else "fallida"),
             resultado.get("conversation_id"), resultado.get("call_sid"),
             resultado.get("error"), req_id))
        conn.commit()
    except Exception:
        conn.rollback()
        log.warning("no se pudo cerrar la solicitud %s", req_id, exc_info=True)
