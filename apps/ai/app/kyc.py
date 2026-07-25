"""KYC / cumplimiento del cierre: documentos del cliente + verificación de identidad.

Persiste (esquema `seguria`, tablas `kyc_document` e `identity_verification`) los
documentos esenciales que el cliente envía para emitir (cédula, autorización firmada,
selfie…) y el veredicto biométrico cédula ↔ selfie (`app/identity.py`).

Expone el *gate* que usa la emisión (`agent_core._emitir_poliza`) para NO cerrar la
venta hasta que estén: (1) los documentos requeridos, (2) la identidad verificada y
(3) los datos obligatorios del catálogo KYC/SARLAFT (`intake.faltantes`). Todo
data-driven; degrada limpio si el motor biométrico no está disponible.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import psycopg

from . import identity

log = logging.getLogger("seguria.kyc")

# Tipos de documento que maneja el flujo (etiqueta legible para el agente/cliente).
DOC_TYPES: dict[str, str] = {
    "cedula_frente": "Cédula (frente)",
    "cedula_reverso": "Cédula (reverso)",
    "selfie": "Selfie / foto de tu rostro",
    "autorizacion_firmada": "Autorización firmada (habeas data / declaración de asegurabilidad)",
    "tarjeta_propiedad": "Tarjeta de propiedad del vehículo",
    "comprobante_pago": "Comprobante de pago",
    "otro": "Otro documento",
}

# Documentos OBLIGATORIOS para emitir. Base para todo producto + extras por tipo.
_REQUIRED_BASE = ("cedula_frente", "selfie", "autorizacion_firmada")
_REQUIRED_POR_TIPO: dict[str, tuple[str, ...]] = {
    "auto": ("tarjeta_propiedad",),
}

# Mapea el insurance_type de la emisión (VIDA/AUTO/SALUD…) a la clave del catálogo.
_TIPO_NORM = {
    "vida": "vida", "auto": "auto", "salud": "salud", "hogar": "hogar",
    "viaje": "viaje", "pyme": "pyme", "accidentes": "accidentes",
}


def normalize_tipo(insurance_type: str | None) -> str:
    return _TIPO_NORM.get(str(insurance_type or "").strip().lower(), "")


def required_docs(insurance_type: str | None) -> list[str]:
    tipo = normalize_tipo(insurance_type)
    return list(_REQUIRED_BASE) + list(_REQUIRED_POR_TIPO.get(tipo, ()))


# ---------------------------------------------------------------- documentos

def register_document(conn: psycopg.Connection, session_key: str, *, tipo: str,
                      file_id: str | None = None, path: str | None = None,
                      filename: str | None = None, mime: str | None = None,
                      extracted: dict | None = None, phone: str | None = None,
                      status: str = "recibido") -> dict[str, Any]:
    """Registra (upsert por session_key+tipo) un documento KYC que envió el cliente."""
    if tipo not in DOC_TYPES:
        tipo = "otro"
    extracted_json = json.dumps(extracted or {}, ensure_ascii=False)
    conn.execute(
        """INSERT INTO kyc_document
               (session_key, phone, tipo, file_id, path, filename, mime, status, extracted, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
           ON CONFLICT (session_key, tipo) DO UPDATE SET
               phone=EXCLUDED.phone, file_id=EXCLUDED.file_id, path=EXCLUDED.path,
               filename=EXCLUDED.filename, mime=EXCLUDED.mime, status=EXCLUDED.status,
               extracted=EXCLUDED.extracted, updated_at=now()""",
        (session_key, phone, tipo, file_id, path, filename, mime, status, extracted_json))
    conn.commit()
    return {"tipo": tipo, "label": DOC_TYPES[tipo], "status": status, "file_id": file_id}


def get_documents(conn: psycopg.Connection, session_key: str) -> dict[str, dict]:
    """Documentos KYC de la sesión, indexados por tipo."""
    try:
        rows = conn.execute(
            "SELECT tipo, file_id, path, filename, mime, status, extracted, updated_at "
            "FROM kyc_document WHERE session_key=%s", (session_key,)).fetchall()
    except Exception:
        conn.rollback()
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        try:
            d["extracted"] = json.loads(d.get("extracted") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["extracted"] = {}
        out[d["tipo"]] = d
    return out


def _doc_path(conn: psycopg.Connection, session_key: str, tipo: str) -> str | None:
    """Ruta física de un documento (usa la guardada; si no, resuelve por file_id)."""
    docs = get_documents(conn, session_key)
    d = docs.get(tipo)
    if not d:
        return None
    if d.get("path"):
        return d["path"]
    fid = d.get("file_id")
    if not fid:
        return None
    try:
        from . import files
        return files.path_for(fid)
    except Exception:
        return None


# ---------------------------------------------------------------- identidad

def record_verification(conn: psycopg.Connection, session_key: str, verdict: dict, *,
                        doc_file_id: str | None = None, selfie_file_id: str | None = None,
                        phone: str | None = None) -> dict[str, Any]:
    """Guarda el veredicto biométrico y, si aprobó, marca cédula+selfie como verificadas."""
    detail = {"reasons": verdict.get("reasons", []),
              "doc_face_score": verdict.get("doc_face_score"),
              "selfie_face_score": verdict.get("selfie_face_score"),
              "available": verdict.get("available")}
    conn.execute(
        """INSERT INTO identity_verification
               (session_key, phone, doc_file_id, selfie_file_id, decision, score, threshold, method, detail)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (session_key, phone, doc_file_id, selfie_file_id, verdict.get("decision"),
         verdict.get("score"), verdict.get("threshold"), verdict.get("method", "yunet_sface"),
         json.dumps(detail, ensure_ascii=False)))
    if verdict.get("decision") == identity.DECISION_APROBADO:
        conn.execute("UPDATE kyc_document SET status='verificado', updated_at=now() "
                     "WHERE session_key=%s AND tipo IN ('cedula_frente','selfie')", (session_key,))
    conn.commit()
    return verdict


def latest_verification(conn: psycopg.Connection, session_key: str) -> dict | None:
    try:
        row = conn.execute(
            "SELECT decision, score, threshold, method, detail, created_at "
            "FROM identity_verification WHERE session_key=%s "
            "ORDER BY created_at DESC LIMIT 1", (session_key,)).fetchone()
    except Exception:
        conn.rollback()
        return None
    if not row:
        return None
    d = dict(row)
    try:
        d["detail"] = json.loads(d.get("detail") or "{}")
    except (json.JSONDecodeError, TypeError):
        d["detail"] = {}
    return d


def run_verification(conn: psycopg.Connection, session_key: str, *,
                     phone: str | None = None, doc_file_id: str | None = None,
                     selfie_file_id: str | None = None) -> dict[str, Any]:
    """Ejecuta la biometría cédula↔selfie de la sesión y persiste el veredicto.

    Toma las rutas de los documentos `cedula_frente` y `selfie` ya registrados
    (o los file_id que se pasen explícitamente). Devuelve el veredicto auditable."""
    docs = get_documents(conn, session_key)
    doc_path = _doc_path(conn, session_key, "cedula_frente")
    selfie_path = _doc_path(conn, session_key, "selfie")

    faltan = []
    if not doc_path:
        faltan.append("cedula_frente")
    if not selfie_path:
        faltan.append("selfie")
    if faltan:
        return {"available": identity.available(), "decision": identity.DECISION_REVISION,
                "score": None, "threshold": None, "method": "yunet_sface",
                "reasons": [f"faltan documentos para comparar: {', '.join(faltan)}"],
                "faltan_documentos": faltan}

    verdict = identity.verify(doc_path, selfie_path)
    record_verification(conn, session_key, verdict,
                        doc_file_id=doc_file_id or (docs.get("cedula_frente") or {}).get("file_id"),
                        selfie_file_id=selfie_file_id or (docs.get("selfie") or {}).get("file_id"),
                        phone=phone)
    return verdict


# ---------------------------------------------------------------- checklist / gate

def _intake_datos(conn: psycopg.Connection, session_key: str) -> dict:
    try:
        row = conn.execute("SELECT datos FROM intake_session WHERE session_key=%s",
                           (session_key,)).fetchone()
        return json.loads(row["datos"]) if row and row["datos"] else {}
    except Exception:
        conn.rollback()
        return {}


def _consent(conn: psycopg.Connection, session_key: str) -> bool:
    try:
        row = conn.execute("SELECT consent FROM checkout_session WHERE session_key=%s",
                           (session_key,)).fetchone()
        return bool(row and row["consent"])
    except Exception:
        conn.rollback()
        return False


def status(conn: psycopg.Connection, session_key: str,
           insurance_type: str | None) -> dict[str, Any]:
    """Estado completo del KYC de la sesión: datos, documentos, identidad y consentimiento.

    Devuelve `listo_para_emitir` y la lista de `faltantes` legibles para que el
    agente sepa exactamente qué pedir a continuación."""
    from . import intake
    tipo = normalize_tipo(insurance_type)
    datos = _intake_datos(conn, session_key)

    # 1) datos obligatorios del catálogo KYC/SARLAFT
    datos_faltantes = [{"id": f["id"], "label": f["label"]} for f in intake.faltantes(tipo, datos)] if tipo else []

    # 2) documentos requeridos
    docs = get_documents(conn, session_key)
    req = required_docs(insurance_type)
    docs_recibidos = [{"tipo": t, "label": DOC_TYPES.get(t, t), "status": docs[t]["status"]}
                      for t in DOC_TYPES if t in docs]
    docs_faltantes = [{"tipo": t, "label": DOC_TYPES.get(t, t)} for t in req if t not in docs]

    # 3) identidad
    ver = latest_verification(conn, session_key)
    identidad = {
        "verificada": bool(ver and ver["decision"] == identity.DECISION_APROBADO),
        "decision": (ver or {}).get("decision"),
        "score": (ver or {}).get("score"),
        "motor_disponible": identity.available(),
    }

    consentimiento = _consent(conn, session_key)

    faltantes: list[str] = []
    if datos_faltantes:
        faltantes += [f"dato: {d['label']}" for d in datos_faltantes[:8]]
    faltantes += [f"documento: {d['label']}" for d in docs_faltantes]
    if not identidad["verificada"]:
        faltantes.append("verificación de identidad (selfie que coincida con la cédula)")
    if not consentimiento:
        faltantes.append("consentimiento de habeas data")

    return {
        "tipo": tipo or None,
        "datos_faltantes": datos_faltantes,
        "documentos_requeridos": [{"tipo": t, "label": DOC_TYPES.get(t, t)} for t in req],
        "documentos_recibidos": docs_recibidos,
        "documentos_faltantes": docs_faltantes,
        "identidad": identidad,
        "consentimiento": consentimiento,
        "faltantes": faltantes,
        "listo_para_emitir": len(faltantes) == 0,
    }


def gate(conn: psycopg.Connection, session_key: str,
         insurance_type: str | None) -> dict[str, Any]:
    """Puerta de cumplimiento para la emisión. `{ok, faltantes, ...}`.

    Comprueba documentos + identidad + datos obligatorios (el consentimiento y el
    pago los valida `_emitir_poliza` por separado). El llamador decide si `KYC_ENFORCE`
    bloquea o solo advierte."""
    st = status(conn, session_key, insurance_type)
    docs_ok = not st["documentos_faltantes"]
    identidad_ok = st["identidad"]["verificada"]
    datos_ok = not st["datos_faltantes"]
    faltantes: list[str] = []
    faltantes += [f"documento: {d['label']}" for d in st["documentos_faltantes"]]
    if not identidad_ok:
        motivo = st["identidad"].get("decision") or "pendiente"
        faltantes.append(f"identidad no verificada ({motivo}): pide una selfie que coincida con la cédula")
    faltantes += [f"dato obligatorio: {d['label']}" for d in st["datos_faltantes"][:8]]
    return {"ok": docs_ok and identidad_ok and datos_ok, "faltantes": faltantes,
            "documentos_ok": docs_ok, "identidad_ok": identidad_ok, "datos_ok": datos_ok,
            "estado": st}
