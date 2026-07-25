"""Documentos firmados de demostración para el expediente del cliente.

Genera un PDF de "Declaración de asegurabilidad" (y, si hay vehículo, una
inspección) por cada intake demo y registra la referencia en
`intake_session.datos.documentos`. El drawer del vendedor los lista y los
descarga vía `/api/documents/{archivo}`.

Nombres de archivo ESTABLES (sin timestamp) e idempotencia: se regeneran en
cada arranque si faltan (DOCS_DIR no es un volumen persistente), sin duplicar
la referencia en la BD. Así el enlace "Ver" nunca queda roto tras un reinicio.
"""
import json
import logging

import psycopg

from .config import DOCS_DIR
from .documents import (BrandPDF, _doc_title, _kv_table, _legal_box, _section)

log = logging.getLogger("seguria.demo_documents")


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())[-10:]


def _build_declaration_pdf(datos: dict, filename: str) -> None:
    """Declaración de asegurabilidad firmada con los datos declarados."""
    pdf = BrandPDF("Declaración", "DEC-" + filename[-8:].replace(".", ""))
    pdf.add_page()
    nombre = datos.get("nombre_completo") or "Cliente"
    _doc_title(
        pdf,
        "Declaración de asegurabilidad",
        nombre,
        "Formulario de datos declarados y consentimiento del tomador",
    )
    rows: list[tuple[str, str]] = []
    campos = [
        ("Documento", datos.get("documento") or datos.get("cedula")),
        ("Fecha de nacimiento", datos.get("fecha_nacimiento")),
        ("Sexo", datos.get("sexo")),
        ("Ciudad", datos.get("ciudad")),
        ("Ocupación", datos.get("ocupacion") or datos.get("actividad_economica")),
        ("Estado civil", datos.get("estado_civil")),
        ("Dependientes", datos.get("dependientes")),
        ("Beneficiarios", datos.get("beneficiarios")),
        ("Fumador", datos.get("fumador")),
        ("Enfermedades", datos.get("enfermedades")),
        ("Preexistencias", datos.get("preexistencias")),
        ("Deportes de riesgo", datos.get("deportes_riesgo")),
    ]
    for label, value in campos:
        if value is not None and str(value).strip() != "":
            rows.append((label, str(value)))
    _section(pdf, "Datos declarados por el tomador")
    _kv_table(pdf, rows)
    _legal_box(pdf, (
        "El tomador declara que la información aquí consignada es veraz y "
        "completa, y autoriza su tratamiento conforme a la política de "
        "protección de datos (Habeas Data). Documento de demostración "
        "generado por el asistente digital de Tequendama."
    ))
    pdf.output(str(DOCS_DIR / filename))


def _build_vehicle_pdf(datos: dict, filename: str) -> None:
    pdf = BrandPDF("Inspección", "INS-" + filename[-8:].replace(".", ""))
    pdf.add_page()
    _doc_title(
        pdf,
        "Inspección de vehículo",
        f"{datos.get('marca', 'Vehículo')} {datos.get('modelo_anio', '')}".strip(),
        "Registro de preinspección para póliza de auto",
    )
    _section(pdf, "Datos del vehículo")
    _kv_table(pdf, [
        ("Marca / Modelo", str(datos.get("marca", "-"))),
        ("Año", str(datos.get("modelo_anio", "-"))),
        ("Placa", str(datos.get("placa", "-")).upper()),
        ("Tenencia", str(datos.get("tenencia", "-"))),
    ])
    _legal_box(pdf, (
        "Preinspección de demostración. La cobertura definitiva queda sujeta "
        "a la inspección física del vehículo por un perito autorizado."
    ))
    pdf.output(str(DOCS_DIR / filename))


def seed_demo_documents(conn: psycopg.Connection) -> None:
    """Genera documentos firmados para los intakes demo y los referencia en
    intake_session.datos.documentos. Idempotente y best-effort."""
    try:
        rows = conn.execute(
            "SELECT session_key, datos FROM intake_session").fetchall()
    except psycopg.Error as exc:
        log.warning("no se pudo leer intake_session: %s", exc)
        return

    for row in rows:
        raw = row["datos"]
        try:
            datos = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (ValueError, TypeError):
            continue
        if not isinstance(datos, dict) or not datos.get("nombre_completo"):
            continue

        phone10 = _digits(row["session_key"])
        if not phone10:
            continue

        documentos: list[dict] = []
        decl_file = f"demo_declaracion_{phone10}.pdf"
        try:
            if not (DOCS_DIR / decl_file).is_file():
                _build_declaration_pdf(datos, decl_file)
            documentos.append({
                "nombre": "Declaración de asegurabilidad",
                "tipo": "Formulario firmado",
                "archivo": decl_file,
                "firmado": True,
                "fecha": str(datos.get("fecha_firma") or "2026-07-22"),
            })
        except Exception as exc:  # noqa: BLE001 - demo best-effort
            log.warning("declaración demo falló (%s): %s", phone10, exc)

        if datos.get("placa") or datos.get("marca"):
            veh_file = f"demo_inspeccion_{phone10}.pdf"
            try:
                if not (DOCS_DIR / veh_file).is_file():
                    _build_vehicle_pdf(datos, veh_file)
                documentos.append({
                    "nombre": "Inspección de vehículo",
                    "tipo": "Preinspección firmada",
                    "archivo": veh_file,
                    "firmado": True,
                    "fecha": "2026-07-22",
                })
            except Exception as exc:  # noqa: BLE001
                log.warning("inspección demo falló (%s): %s", phone10, exc)

        if documentos:
            datos["documentos"] = documentos
            conn.execute(
                "UPDATE intake_session SET datos = %s WHERE session_key = %s",
                (json.dumps(datos, ensure_ascii=False), row["session_key"]))
    conn.commit()
