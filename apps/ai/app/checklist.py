"""Checklist de activación: el "camino" único y de larga duración que reemplaza
el cierre en vivo (KYC → firma → pago) como uno por uno en el chat.

En vez de que Mónica/Sofía llamen 4 herramientas separadas dentro de la misma
conversación (`generar_verificacion_identidad` → `evaluar_riesgo` →
`generar_firma_poliza` → `generar_link_pago`), le entregan al cliente un único
link (`/activacion/{token}`, servido por el frontend React) que vive PARA
SIEMPRE — a diferencia de los links internos de cada paso (KYC/firma tienen
TTL corto, ver `kyc.py`/`esign.py`). El cliente avanza a su ritmo; cada paso
siguiente se crea recién cuando el anterior queda resuelto (nunca los 3 de
una), para no gastar sesiones de Didit/Polar que nadie abre.

Flujo secuencial: 1) identidad (Didit KYC), 2) underwriting (automático, no es
un paso que el cliente vea — decide si sigue a firma o si el caso se va a
revisión humana), 3) firma electrónica, 4) pago (Polar). Reusa `kyc.py`/
`esign.py`/`payments.py`/`underwriting.py` tal cual — este módulo no
duplica esa lógica, solo orquesta CUÁNDO se dispara cada uno.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone

import psycopg
import requests
from fastapi import APIRouter, HTTPException

from .config import (BACKEND_URL, CHECKLIST_STALL_HOURS, FRONTEND_PUBLIC_URL,
                    PUBLIC_BASE_URL)
from .underwriting import AUTO_APPROVE, DECLINE, REFER

log = logging.getLogger("seguria.checklist")

router = APIRouter()

_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)


def _token_hash(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def _tables(conn: psycopg.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS activacion_checklist (
        checklist_id TEXT PRIMARY KEY,
        session_key TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        quote_id TEXT,
        insurance_type TEXT,
        monthly_premium_cop DOUBLE PRECISION,
        modalidad TEXT DEFAULT 'individual',
        token_hash TEXT UNIQUE NOT NULL,
        underwriting_decision TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_activacion_checklist_session
                    ON activacion_checklist (session_key)""")


# ---------- Entrega (empuje activo por WhatsApp/correo, mismo patrón que
# esign._deliver / kyc._deliver — duplicado a propósito, no se importa) ------

def _deliver(url: str | None, texto: str, asunto: str, *, phone: str | None,
            email: str | None) -> dict:
    sent_via: list[str] = []
    if phone:
        try:
            from . import whatsapp_gateway
            if whatsapp_gateway.enviar_whatsapp(phone, texto):
                sent_via.append("whatsapp")
        except Exception:
            log.warning("no se pudo enviar el link del checklist por WhatsApp", exc_info=True)
    if email:
        try:
            import asyncio

            from .email_service import send_email
            html = f"<p>{texto}</p>" + (f"<p><a href='{url}'>{url}</a></p>" if url else "")
            result = asyncio.run(send_email(email, asunto, html, text=texto))
            if result.get("status") == "sent":
                sent_via.append("email")
            else:
                # skipped/error NO son excepciones: sin este log el motivo
                # real (circuito abierto, dominio sin verificar, 403 de
                # Resend) se perdía y "los correos no llegan" quedaba mudo.
                log.warning("correo del checklist a %s no salió: %s (%s)", email,
                            result.get("status"), result.get("reason"))
        except Exception:
            log.warning("no se pudo enviar el link del checklist por correo", exc_info=True)
    return {"sent_via": sent_via}


def _avisar(texto: str, *, phone: str | None, email: str | None) -> dict:
    """Aviso simple SIN link (el cliente ya tiene su link del checklist
    guardado/abierto — no hace falta reenviarlo para un aviso de transición de
    paso). Usado dentro de `avanzar()`; distinto de `reenviar_paso_actual`, que
    sí rota y reenvía la URL para el caso de Camila."""
    return _deliver(None, f"Tequendama Seguros: {texto}. Revisa el checklist que ya tienes.",
                    "Tu activación — Tequendama Seguros", phone=phone, email=email)


def _rotar_y_avisar(conn: psycopg.Connection, checklist_id: str, texto: str, *,
                    phone: str | None, email: str | None,
                    quote_id: str | None = None) -> dict:
    """Rota el token del checklist (el crudo no es recuperable de la fila, solo
    se guarda su hash — igual que KYC/firma) y reenvía la URL fresca. SOLO para
    el reenvío explícito que pide Camila antes de llamar — nunca durante un
    /refrescar disparado por el propio cliente, porque invalidaría el link que
    tiene abierto en ese mismo momento (ver `_avisar`)."""
    token = secrets.token_urlsafe(32)
    conn.execute("UPDATE activacion_checklist SET token_hash=%s, updated_at=now() "
                "WHERE checklist_id=%s", (_token_hash(token), checklist_id))
    conn.commit()
    url = f"{FRONTEND_PUBLIC_URL}/activacion/{token}"
    cuerpo = f"Tequendama Seguros: {texto}. Este es tu link, no vence:\n{url}"
    ficha = _quote_info(conn, quote_id)
    if ficha and ficha.get("pdf_url"):
        cuerpo += f"\n\nTambién puedes revisar la ficha de tu seguro aquí: {ficha['pdf_url']}"
    return _deliver(url, cuerpo, "Tu activación — Tequendama Seguros", phone=phone, email=email)


def _notify_referral(tenant_id: str, checklist_id: str, uw: dict, nombre: str | None) -> None:
    """Alerta al gerente cuando el underwriting automático del checklist da
    REFER — mismo patrón que agent_core._notify_referral / kyc._notify_manual_review,
    duplicado (no importado) siguiendo el criterio ya establecido en este repo
    para alertas cruzadas entre módulos autocontenidos."""
    try:
        msg = (f"Checklist de activación ({checklist_id}): {nombre or 'cliente'} — "
              f"seguro de {uw.get('tipo', '').lower()} por {uw.get('prima_cop', 0):,.0f} "
              f"COP/mes requiere aprobación humana. Motivos: {'; '.join(uw.get('reasons', []))}")
        payload = {"message": msg[:900], "severity": "alta"}
        if _UUID4_RE.match(tenant_id or ""):
            payload["teamId"] = tenant_id
        requests.post(f"{BACKEND_URL}/api/v1/alerts", json=payload, timeout=5,
                     headers={"X-Tenant-Id": tenant_id})
    except Exception:
        log.debug("no se pudo crear la alerta de underwriting del checklist", exc_info=True)


# ---------- Creación ----------

def get_or_create(conn: psycopg.Connection, session_key: str, tenant_id: str, *,
                  phone: str | None, email: str | None, quote_id: str | None,
                  insurance_type: str | None, monthly_premium_cop: float | None,
                  modalidad: str = "individual") -> dict:
    """Idempotente: si ya existe un checklist para esta sesión, lo devuelve
    SIN reenviar nada (mismo criterio de `generar_firma_poliza`/
    `generar_verificacion_identidad` — no se re-muestra un link ya entregado).

    `modalidad="asesor"` (producto de alta fricción, no autogestionable — ver
    Nota_estrategica_Seguros_Colsubsidio.pdf) NO crea checklist: el llamador
    (agent_core.py) debe derivar a un asesor humano en su lugar."""
    if modalidad == "asesor":
        return {"created": False, "error": "este producto requiere asesoría humana; "
                                          "no se ofrece un checklist autogestionado"}
    _tables(conn)
    row = conn.execute("SELECT * FROM activacion_checklist WHERE session_key=%s",
                       (session_key,)).fetchone()
    if row:
        return {"created": False, "checklist_id": row["checklist_id"]}

    checklist_id = f"chk_{uuid.uuid4().hex[:12]}"
    token = secrets.token_urlsafe(32)
    url = f"{FRONTEND_PUBLIC_URL}/activacion/{token}"
    if not FRONTEND_PUBLIC_URL:
        log.warning("FRONTEND_PUBLIC_URL vacío: el link del checklist (%s) no será absoluto", url)

    conn.execute(
        """INSERT INTO activacion_checklist
               (checklist_id, session_key, tenant_id, phone, email, quote_id,
                insurance_type, monthly_premium_cop, modalidad, token_hash)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (checklist_id, session_key, tenant_id, phone, email, quote_id,
         insurance_type, monthly_premium_cop, modalidad, _token_hash(token)))
    conn.commit()

    pasos_txt = ("Solo firmas y pagas — al ser un plan colectivo con aceptación "
                "garantizada, no necesitas subir documentos ni hacer verificación "
                "facial." if modalidad == "colectiva" else
                "Primero verificas tu identidad (cédula + reconocimiento facial), "
                "luego firmas y por último pagas.")
    texto = ("Tequendama Seguros: aquí tienes tu link único para activar tu póliza. "
             f"Complétalo a tu ritmo, cuando quieras — no vence:\n{url}\n\n{pasos_txt}")
    ficha = _quote_info(conn, quote_id)
    if ficha and ficha.get("pdf_url"):
        texto += f"\n\nTambién puedes revisar la ficha de tu seguro aquí: {ficha['pdf_url']}"
    entrega = _deliver(url, texto, "Activa tu póliza — Tequendama Seguros",
                       phone=phone, email=email)
    if not entrega.get("sent_via"):
        # El link existe pero NO le llegó por ningún canal (correo caído,
        # WhatsApp sin gateway…). Devolverlo permite al agente entregar la
        # URL en pantalla en vez de mentirle al cliente con "ya te lo envié".
        log.warning("checklist %s creado pero sin entrega (phone=%s email=%s)",
                    checklist_id, bool(phone), bool(email))
    return {"created": True, "checklist_id": checklist_id,
            "sent_via": entrega.get("sent_via", []), "url": url}


def by_token(conn: psycopg.Connection, token: str) -> dict | None:
    _tables(conn)
    row = conn.execute("SELECT * FROM activacion_checklist WHERE token_hash=%s",
                       (_token_hash(token),)).fetchone()
    return dict(row) if row else None


def latest_by_session(conn: psycopg.Connection, session_key: str) -> dict | None:
    _tables(conn)
    row = conn.execute(
        """SELECT * FROM activacion_checklist WHERE session_key=%s
           ORDER BY created_at DESC LIMIT 1""", (session_key,)).fetchone()
    return dict(row) if row else None


# ---------- Estado / avance ----------

def _perfil(conn: psycopg.Connection, session_key: str):
    try:
        from . import profiling
        from .agent_core import _get_checkout, _get_intake
        datos = {**_get_intake(conn, session_key), **_get_checkout(conn, session_key)}
        return profiling.build_profile(datos) if datos else None
    except Exception:
        log.debug("perfil no disponible para el checklist", exc_info=True)
        return None


def _quote_info(conn: psycopg.Connection, quote_id: str | None) -> dict | None:
    """Ficha ya generada de la cotización de esta sesión (PDF + coberturas) —
    ver `generar_documento`/`build_quote_pdf` en agent_core.py/documents.py.
    Reusa la MISMA ficha (guardada en `quotes.document_url`), no genera una
    nueva; si el cliente nunca pidió el PDF todavía, `pdf_url` viene None."""
    if not quote_id:
        return None
    try:
        row = conn.execute(
            """SELECT q.document_url, p.nombre producto, p.coberturas, p.aseguradora
               FROM quotes q JOIN products p ON p.id = q.product_id
               WHERE q.id = %s::bigint""", (quote_id,)).fetchone()
    except Exception:
        conn.rollback()
        return None
    if not row:
        return None
    import json as _json
    try:
        coberturas = _json.loads(row["coberturas"]) if row.get("coberturas") else []
    except (TypeError, ValueError):
        coberturas = []
    pdf_url = row.get("document_url")
    if pdf_url and pdf_url.startswith("/"):
        pdf_url = f"{PUBLIC_BASE_URL}{pdf_url}"
    return {"pdf_url": pdf_url, "producto": row.get("producto"),
           "aseguradora": row.get("aseguradora"), "coberturas": coberturas}


def _pasos(kyc_row: dict | None, kyc_url: str | None, uw_decision: str | None,
          esign_row, esign_url: str | None, pago_row: dict | None,
          modalidad: str = "individual") -> tuple[str, list[dict]]:
    """Checkpoints del checklist. Para `modalidad="individual"` (default): el
    link, cédula (OCR) y reconocimiento facial (liveness+face match) como
    pasos DISTINTOS dentro de la misma sesión de Didit — kyc.py ya guarda
    `document_number`/`liveness_status`/`face_match_status` en cuanto Didit
    los reporta, incluso antes del veredicto final (ver
    kyc.refresh_decision) — luego firma y pago.

    Para `modalidad="colectiva"` (póliza colectiva, aceptación garantizada —
    ver Nota_estrategica_Seguros_Colsubsidio.pdf §1/§5): SIN biometría, la
    identidad ya quedó cubierta con el documento capturado en
    `capturar_datos_cliente` — el checklist salta directo de link a firma."""
    from . import esign as esign_mod
    from . import kyc as kyc_mod

    pasos: list[dict] = [{"id": "link", "estado": "completado", "url": None}]

    if modalidad == "colectiva":
        identidad_lista, identidad_fallida = True, False
        cedula_hecha = rf_hecha = True  # no aplica; solo para el mensaje de abajo
    else:
        cedula_hecha = bool(kyc_row and kyc_row.get("document_number"))
        rf_hecha = bool(kyc_row and kyc_row.get("liveness_status") and kyc_row.get("face_match_status"))
        identidad_ok = bool(kyc_row and kyc_row["status"] == kyc_mod.APROBADO)
        identidad_fallida = bool(kyc_row and kyc_row["status"] in (kyc_mod.RECHAZADO, kyc_mod.EXPIRADO))
        identidad_lista = cedula_hecha and rf_hecha and identidad_ok

        cedula_estado = "completado" if cedula_hecha else "actual"
        rf_estado = "completado" if rf_hecha else ("actual" if cedula_hecha else "bloqueado")
        pasos.append({"id": "cedula", "estado": cedula_estado, "url": kyc_url})
        pasos.append({"id": "reconocimiento_facial", "estado": rf_estado, "url": kyc_url})

    firma_estado = pago_estado = "bloqueado"

    if not identidad_lista:
        if identidad_fallida:
            paso_actual = "rechazado"
        else:
            paso_actual = "cedula" if not cedula_hecha else "reconocimiento_facial"
    elif uw_decision == REFER:
        paso_actual = "en_revision"
    elif uw_decision == DECLINE:
        paso_actual = "rechazado"
    else:
        firmado = bool(esign_row and esign_row.get("status") == esign_mod.SIGNED)
        firma_estado = "completado" if firmado else "actual"
        if not firmado:
            paso_actual = "firma"
        else:
            pagado = bool(pago_row and pago_row.get("status") == "APPROVED")
            pago_estado = "completado" if pagado else "actual"
            paso_actual = "completado" if pagado else "pago"

    pasos.append({"id": "firma", "estado": firma_estado, "url": esign_url})
    pasos.append({"id": "pago", "estado": pago_estado,
                 "url": (pago_row or {}).get("checkout_url")})
    return paso_actual, pasos


def _avanzar_locked(conn: psycopg.Connection, row: dict) -> dict:
    """Debe correr bajo pg_advisory_xact_lock(session_key) — ver `avanzar`."""
    from . import esign, kyc, payments

    session_key, tenant_id = row["session_key"], row["tenant_id"]
    phone, email = row.get("phone"), row.get("email")
    modalidad = row.get("modalidad") or "individual"

    if modalidad == "colectiva":
        # Póliza colectiva con aceptación garantizada: sin biometría/KYC — el
        # documento de identidad ya se capturó con capturar_datos_cliente
        # (ver Nota_estrategica_Seguros_Colsubsidio.pdf §1/§5).
        kyc_row, kyc_url, identidad_lista = None, None, True
    else:
        kyc_row = kyc.latest_for_session(conn, session_key)
        kyc_url = None
        if kyc_row is None:
            result = kyc.request_verification(conn, session_key, tenant_id, phone=phone,
                                              email=email, include_url=True)
            kyc_url = result.get("link_url")
            kyc_row = kyc.latest_for_session(conn, session_key)
        identidad_lista = bool(kyc_row and kyc_row["status"] == kyc.APROBADO)

    uw_decision = row.get("underwriting_decision")
    esign_row, esign_url, pago_row = None, None, None

    if identidad_lista:
        if uw_decision is None:
            uw = evaluate_underwriting(conn, session_key, row)
            uw_decision = uw["decision"]
            conn.execute(
                "UPDATE activacion_checklist SET underwriting_decision=%s, updated_at=now() "
                "WHERE checklist_id=%s", (uw_decision, row["checklist_id"]))
            conn.commit()
            if uw_decision == REFER:
                _notify_referral(tenant_id, row["checklist_id"], uw, kyc_row.get("full_name"))

        if uw_decision == AUTO_APPROVE:
            esign_row = esign.latest_pending(conn, session_key, "autorizacion_poliza") or \
                (None if not esign.is_signed(conn, session_key, "autorizacion_poliza")
                 else {"status": esign.SIGNED})
            if esign_row is None:
                view = esign.request_signature(conn, session_key, tenant_id,
                                                purpose="autorizacion_poliza",
                                                phone=phone, email=email)
                esign_url = view.get("sign_url")
                esign_row = {"status": view.get("status")}
                _avisar("ya puedes continuar: firma tu póliza", phone=phone, email=email)

            if esign_row.get("status") == esign.SIGNED:
                pago_row = payments._latest(conn, session_key)
                if pago_row is None:
                    pago_row = payments.generar_link_pago(
                        conn, session_key, tenant_id,
                        {"monto_cop": row.get("monthly_premium_cop"),
                         "descripcion": f"Primera mensualidad — "
                                        f"{row.get('insurance_type') or 'seguro'}"})
                    _avisar("ya puedes continuar: paga tu póliza", phone=phone, email=email)

    return _pasos(kyc_row, kyc_url, uw_decision, esign_row, esign_url, pago_row, modalidad)


def evaluate_underwriting(conn: psycopg.Connection, session_key: str, row: dict) -> dict:
    from . import underwriting
    return underwriting.evaluate(
        _perfil(conn, session_key),
        insurance_type=str(row.get("insurance_type") or ""),
        monthly_premium_cop=row.get("monthly_premium_cop") or 0,
        modalidad=row.get("modalidad") or "individual")


def avanzar(conn: psycopg.Connection, row: dict) -> dict:
    """Chequea el paso actual y crea (una sola vez) el siguiente si el gate ya
    se abrió. Bajo advisory lock por sesión — evita que dos requests
    concurrentes (ej. el poll de la llamada saliente y la pestaña del cliente)
    dupliquen una firma o un checkout de pago.

    Usa `pg_advisory_lock` (de SESIÓN, no `pg_advisory_xact_lock`): dentro de
    `_avanzar_locked` hay varios `conn.commit()` intermedios (de kyc.py/
    esign.py/payments.py, cada uno gestiona su propia transacción) — un lock
    de TRANSACCIÓN se liberaría en el primero de esos commits y dejaría de
    proteger el resto de la función. El de sesión sobrevive a los commits y se
    libera explícitamente en el `finally`.

    Re-lee la fila DESPUÉS de tomar el lock (no confía en el `row` que trajo
    el llamador): si `row` viene de un fetch anterior (ej. el caller lo
    guardó y llama `avanzar` varias veces con la misma copia), `underwriting_
    decision` seguiría viéndose NULL para siempre y el guard de
    `_avanzar_locked` ("solo evalúa/alerta si es None") se re-dispararía en
    cada llamada — justo el bug que expuso la prueba de "REFER se alerta una
    sola vez" al reusar la misma copia de `row` en 5 llamadas seguidas."""
    conn.execute("SELECT pg_advisory_lock(hashtext(%s))", (row["session_key"],))
    try:
        fresh = conn.execute("SELECT * FROM activacion_checklist WHERE checklist_id=%s",
                             (row["checklist_id"],)).fetchone()
        row = dict(fresh) if fresh else row
        paso_actual, pasos = _avanzar_locked(conn, row)
    finally:
        # Si _avanzar_locked reventó con un error de BD, la transacción queda
        # abortada y CUALQUIER comando (incluido el unlock) fallaría con
        # InFailedSqlTransaction hasta hacer rollback. El advisory lock de
        # SESIÓN no se libera con el rollback (solo con el unlock explícito o
        # el cierre de la conexión), así que esto es seguro y necesario.
        try:
            conn.rollback()
        except Exception:
            pass
        conn.execute("SELECT pg_advisory_unlock(hashtext(%s))", (row["session_key"],))
    return {"paso_actual": paso_actual, "pasos": pasos,
           "ficha": _quote_info(conn, row.get("quote_id")),
           "actualizado_en": datetime.now(timezone.utc).isoformat()}


def estado_actual(conn: psycopg.Connection, row: dict) -> dict:
    """Lectura PURA (sin escribir nada) — para el GET público. No crea ni
    reenvía ningún paso; eso solo pasa en `avanzar` (POST /refrescar), para
    que un escáner de links de correo no dispare pasos reales con un simple
    GET automático."""
    from . import esign, kyc, payments

    session_key = row["session_key"]
    modalidad = row.get("modalidad") or "individual"
    kyc_row = None if modalidad == "colectiva" else kyc.latest_for_session(conn, session_key)
    uw_decision = row.get("underwriting_decision")
    esign_row = None
    pago_row = None
    if uw_decision == AUTO_APPROVE:
        pending = esign.latest_pending(conn, session_key, "autorizacion_poliza")
        esign_row = pending or ({"status": esign.SIGNED}
                                if esign.is_signed(conn, session_key, "autorizacion_poliza")
                                else None)
        if esign_row and esign_row.get("status") == esign.SIGNED:
            pago_row = payments._latest(conn, session_key)

    paso_actual, pasos = _pasos(kyc_row, None, uw_decision, esign_row, None, pago_row, modalidad)
    return {"paso_actual": paso_actual, "pasos": pasos,
           "nombre_cliente": (kyc_row or {}).get("full_name"),
           "ficha": _quote_info(conn, row.get("quote_id")),
           "actualizado_en": row.get("updated_at").isoformat()
                              if row.get("updated_at") else None}


def stalled(conn: psycopg.Connection) -> list[dict]:
    """Checklists sin avanzar hace `CHECKLIST_STALL_HOURS` o más, que no están
    ni rechazados ni completados — candidatos para que Camila reactive con una
    llamada (ver `proactive.checklist_nudges`)."""
    _tables(conn)
    rows = conn.execute(
        """SELECT checklist_id, session_key, tenant_id, phone, underwriting_decision,
                  EXTRACT(EPOCH FROM (now() - updated_at)) / 3600.0 AS horas_sin_avanzar
           FROM activacion_checklist
           WHERE updated_at < now() - (%s || ' hours')::interval
           ORDER BY updated_at ASC""", (CHECKLIST_STALL_HOURS,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("underwriting_decision") == DECLINE:
            continue  # rechazado: no tiene sentido reactivar
        pago = conn.execute(
            "SELECT status FROM payment_session WHERE session_key=%s "
            "ORDER BY created_at DESC LIMIT 1", (d["session_key"],)).fetchone()
        if pago and pago["status"] == "APPROVED":
            continue  # ya completó y pagó
        out.append(d)
    return out


def reenviar_paso_actual(conn: psycopg.Connection, row: dict) -> dict:
    """Reenvía (rotando el token — ver `_rotar_y_avisar`) el link del checklist
    — lo usa Camila (llamada saliente) justo antes de marcar, para que el
    cliente tenga el link a mano durante la llamada."""
    _tables(conn)
    estado = estado_actual(conn, row)
    texto = {
        "cedula": "te reenvío el link para verificar tu identidad (cédula) y activar tu póliza",
        "reconocimiento_facial": "te reenvío el link: ya subiste tu cédula, falta el "
                                 "reconocimiento facial para verificar tu identidad",
        "en_revision": "tu caso está en revisión de un asesor, te confirmamos pronto",
        "rechazado": "hablemos de otras opciones de protección para ti",
        "firma": "te reenvío el link para continuar: ya puedes firmar tu póliza",
        "pago": "te reenvío el link para continuar: ya puedes pagar tu póliza",
        "completado": "tu póliza ya está lista",
    }.get(estado["paso_actual"], "retomemos tu proceso de activación")
    return _rotar_y_avisar(conn, row["checklist_id"], texto, phone=row.get("phone"),
                           email=row.get("email"), quote_id=row.get("quote_id"))


# ---------- Endpoints públicos (sin auth — mismo criterio que /kyc/{token},
# /sign/{token}, /api/embedded/*) ----------

@router.get("/api/checklist/{token}")
def get_checklist(token: str):
    from .db import get_conn
    conn = get_conn()
    try:
        row = by_token(conn, token)
        if row is None:
            raise HTTPException(status_code=404, detail="checklist no encontrado")
        return estado_actual(conn, row)
    finally:
        conn.close()


@router.post("/api/checklist/{token}/refrescar")
def refrescar_checklist(token: str):
    from .db import get_conn
    conn = get_conn()
    try:
        row = by_token(conn, token)
        if row is None:
            raise HTTPException(status_code=404, detail="checklist no encontrado")
        return avanzar(conn, row)
    finally:
        conn.close()
