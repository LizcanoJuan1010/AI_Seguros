"""Solicitudes de llamada desde la landing pública ("déjanos tu número y te llamamos").

A diferencia de `/api/calls/outbound` (que exige X-Service-Key y la dispara un
gerente desde el CRM o el cron proactivo), esta puerta es ANÓNIMA: la usa
cualquiera que entre a la página de inicio. Eso obliga a tres cosas que el
endpoint interno no necesita:

  1. Normalizar y validar el número (E.164; Colombia por defecto) — el usuario
     escribe "300 123 4567", "3001234567" o "+57 300 123 4567".
  2. Registrar el consentimiento explícito de contacto telefónico (Ley 1581/2012
     y Ley 1581 art. 5 para el dato de contacto). Sin `consent=true` no se llama.
  3. Limitar el abuso. Es un endpoint público que gasta minutos de telefonía: sin
     tope, cualquiera puede usarlo para llamar a un tercero a repetición.

PENDIENTE ANTES DE PRODUCCIÓN — verificación del número por OTP. Hoy nada impide
escribir el número de otra persona; lo único que lo contiene es que la cuenta de
Twilio en trial solo marca a números verificados a mano en su consola. En el
momento en que se salga de trial, hay que exigir un código enviado por SMS/
WhatsApp antes de llamar (el gancho natural es entre `registrar` y `disparar`).

La llamada en sí la hace `calls.iniciar_llamada` (ElevenLabs), igual que el
resto del stack — y como allá, sin credenciales corre en modo demo: registra la
solicitud, no llama a nadie, no rompe nada.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import psycopg

from .config import (CALLBACK_HORARIO_ENFORCE, CALLBACK_HORA_FIN,
                     CALLBACK_HORA_INICIO, CALLBACK_MAX_POR_DISPOSITIVO,
                     CALLBACK_MAX_POR_IP, CALLBACK_MAX_POR_TELEFONO,
                     DEFAULT_COUNTRY_CODE)

log = logging.getLogger("seguria.callback")

# Intereses que ofrece la landing (mismos ramos que ProductCards.tsx). Se valida
# contra esta lista para que no entre texto libre a las dynamic_variables del
# agente de voz.
INTERESES = {
    "vida": "Seguro de Vida",
    "auto": "Seguro de Auto",
    "salud": "Seguro de Salud",
    "hogar": "Seguro de Hogar",
    "otro": "Todavía no lo tengo claro",
}

# Colombia: celulares de 10 dígitos que empiezan por 3. Fijos con indicativo.
_SOLO_DIGITOS = re.compile(r"\D+")


def normalizar_telefono(raw: str, *, cc: str = "") -> str | None:
    """"300 123 4567" / "3001234567" / "+57 300 123 4567" -> "+573001234567".

    Devuelve None si no parece un número marcable. Acepta ya-en-E.164 de
    cualquier país (por si mañana la landing sirve a más de Colombia), pero
    para un número local asume `cc` (default DEFAULT_COUNTRY_CODE)."""
    s = (raw or "").strip()
    if not s:
        return None
    tiene_mas = s.startswith("+")
    digitos = _SOLO_DIGITOS.sub("", s)
    if not digitos:
        return None

    cc = (cc or DEFAULT_COUNTRY_CODE).lstrip("+")
    if tiene_mas:
        # Ya venía internacional: confiamos en lo que escribió.
        return f"+{digitos}" if 8 <= len(digitos) <= 15 else None
    if digitos.startswith(cc) and len(digitos) > 10:
        # Escribió el indicativo sin el "+" (ej. 573001234567).
        return f"+{digitos}"
    if len(digitos) == 10:
        return f"+{cc}{digitos}"
    return None


def es_celular_colombiano(phone: str) -> bool:
    """True si es un celular colombiano (+57 3XXXXXXXXX). El agente de voz solo
    tiene sentido en móvil: a un fijo de oficina no le sirve el flujo."""
    return bool(re.fullmatch(r"\+573\d{9}", phone or ""))


def _tabla(conn: psycopg.Connection) -> None:
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
    if not valor:
        return 0
    desde = datetime.now(timezone.utc) - timedelta(hours=1)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM callback_request WHERE {campo}=%s AND created_at >= %s",
        (valor, desde)).fetchone()
    return int(row["n"]) if row else 0


# (columna, límite, mensaje) — el orden importa: se reporta el primero que topa.
def _limites() -> list[tuple[str, int, str]]:
    return [
        ("phone", CALLBACK_MAX_POR_TELEFONO,
         "Ya solicitaste varias llamadas a este número en la última hora. "
         "Espera un momento y vuelve a intentarlo."),
        ("device_id", CALLBACK_MAX_POR_DISPOSITIVO,
         "Demasiadas solicitudes desde este navegador en la última hora."),
        ("ip", CALLBACK_MAX_POR_IP,
         "Demasiadas solicitudes desde esta conexión en la última hora."),
    ]


def _en_horario() -> bool:
    """Horario hábil de Colombia (UTC-5, sin horario de verano). Con
    CALLBACK_HORARIO_ENFORCE=false (default) siempre devuelve True — el demo
    tiene que poder correr a cualquier hora."""
    if not CALLBACK_HORARIO_ENFORCE:
        return True
    hora = (datetime.now(timezone.utc) - timedelta(hours=5)).hour
    return CALLBACK_HORA_INICIO <= hora < CALLBACK_HORA_FIN


def _registrar(conn: psycopg.Connection, **campos) -> int | None:
    """Deja la solicitud en `callback_request` (auditoría del consentimiento) y
    devuelve su id. Nunca lanza: si la BD falla, la llamada igual se dispara."""
    try:
        _tabla(conn)
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


def _cerrar(conn: psycopg.Connection, req_id: int | None, resultado: dict) -> None:
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


def solicitar(conn: psycopg.Connection, *, telefono: str, nombre: str = "",
              interes: str = "", device_id: str = "", tenant_id: str,
              consent: bool = False, ip: str = "", user_agent: str = "") -> dict:
    """Valida, registra y dispara la llamada saliente al número que dejó el
    visitante. Devuelve siempre un dict con `ok` y un `mensaje` listo para
    mostrar en la landing — los errores de validación son 200 con ok=False para
    que el front los pinte en el formulario sin tratarlos como caída."""
    phone = normalizar_telefono(telefono)
    if not phone or not es_celular_colombiano(phone):
        return {"ok": False, "motivo": "telefono_invalido",
                "mensaje": "Escribe un celular colombiano válido, de 10 dígitos "
                           "(por ejemplo 300 123 4567)."}
    if not consent:
        return {"ok": False, "motivo": "sin_consentimiento",
                "mensaje": "Necesitamos tu autorización para poder llamarte."}
    if not _en_horario():
        return {"ok": False, "motivo": "fuera_de_horario",
                "mensaje": f"Llamamos entre las {CALLBACK_HORA_INICIO}:00 y las "
                           f"{CALLBACK_HORA_FIN}:00. Déjanos tu número más tarde "
                           "o escríbenos por WhatsApp mientras tanto."}

    _tabla(conn)
    for campo, tope, mensaje in _limites():
        valor = {"phone": phone, "device_id": device_id, "ip": ip}[campo]
        if valor and _cuenta_ultima_hora(conn, campo, valor) >= tope:
            log.info("callback bloqueado por límite de %s (%s)", campo, valor)
            return {"ok": False, "motivo": f"limite_{campo}", "mensaje": mensaje}

    interes = interes if interes in INTERESES else ""
    nombre = (nombre or "").strip()[:80]

    req_id = _registrar(conn, phone=phone, nombre=nombre or None,
                        interes=interes or None, device_id=device_id or None,
                        tenant_id=tenant_id, consent=True, ip=ip or None,
                        user_agent=(user_agent or "")[:300] or None,
                        status="solicitada")

    # Contexto para el agente de voz. `calls.iniciar_llamada` ya agrega lo que
    # el cliente haya cotizado antes en el chat (`_sale_context`) cruzando por
    # este mismo teléfono; lo de acá gana sobre eso porque es lo que acaba de
    # decirnos en el formulario.
    variables: dict[str, str] = {"origen": "landing"}
    if nombre:
        variables["nombre_cliente"] = nombre
    if interes:
        variables["interes"] = INTERESES[interes]

    saludo = None
    if nombre and interes:
        saludo = (f"Hola {nombre.split()[0]}, te llamo de Tequendama Seguros. "
                  f"Vi que dejaste tu número porque te interesa el "
                  f"{INTERESES[interes].lower()}. ¿Tienes un minuto?")
    elif nombre:
        saludo = (f"Hola {nombre.split()[0]}, te llamo de Tequendama Seguros "
                  "porque dejaste tu número en nuestra página. ¿Tienes un minuto?")

    from . import calls
    resultado = calls.iniciar_llamada(phone, tenant_id, first_message=saludo,
                                      dynamic_variables=variables)
    _cerrar(conn, req_id, resultado)

    # El lead entra al CRM aunque la llamada falle: el visitante ya dio su
    # número y su interés, eso es un lead real. Best-effort, como el resto de
    # los puentes al backend.
    try:
        from . import backend_client
        backend_client.upsert_lead(tenant_id, phone,
                                   insurance_type=interes.upper() if interes in
                                   ("vida", "auto", "salud") else None,
                                   status="NUEVO")
    except Exception:
        log.debug("no se pudo crear el lead de la solicitud de llamada", exc_info=True)

    if resultado.get("demo"):
        return {"ok": True, "demo": True, "solicitud_id": req_id,
                "mensaje": "Solicitud registrada. La llamada está en modo demo: "
                           "faltan las credenciales de telefonía."}
    if not resultado.get("ok"):
        return {"ok": False, "motivo": "telefonia", "solicitud_id": req_id,
                "mensaje": "No pudimos iniciar la llamada en este momento. "
                           "Inténtalo de nuevo en un par de minutos."}
    return {"ok": True, "demo": False, "solicitud_id": req_id,
            "conversation_id": resultado.get("conversation_id"),
            "mensaje": "Te estamos llamando ahora mismo. Contesta cuando suene."}
