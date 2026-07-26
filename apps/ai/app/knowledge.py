"""Conocimiento del negocio editable por gerencia (tabla agent_knowledge).

El panel "Agente IA" del dashboard gerencial crea/edita entradas (promos
vigentes, políticas comerciales, respuestas oficiales, cambios de precio
explicados...). Las entradas ACTIVAS del tenant se inyectan al system prompt
de todas las conversaciones del agente (cliente y gerente) en
`agent_core.run_agent`, de modo que actualizar el conocimiento del agente es
editar una fila — sin tocar código ni re-desplegar.
"""
import logging

import psycopg

from .db import get_conn

log = logging.getLogger("seguria.knowledge")

# El prompt no debe crecer sin límite: se inyectan las N entradas más
# recientes y cada contenido se recorta.
MAX_ENTRIES_IN_PROMPT = 12
MAX_CONTENT_CHARS = 1500


def list_entries(tenant_id: str, *, include_inactive: bool = True) -> list[dict]:
    conn = get_conn()
    try:
        where = "WHERE tenant_id = %s" + ("" if include_inactive else " AND active")
        rows = conn.execute(
            f"""SELECT id, title, content, active, updated_at
                FROM agent_knowledge {where}
                ORDER BY updated_at DESC""",
            (tenant_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_entry(tenant_id: str, title: str, content: str) -> dict:
    conn = get_conn()
    try:
        row = conn.execute(
            """INSERT INTO agent_knowledge (tenant_id, title, content)
               VALUES (%s, %s, %s)
               RETURNING id, title, content, active, updated_at""",
            (tenant_id, title.strip(), content.strip())).fetchone()
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def update_entry(tenant_id: str, entry_id: int, *, title: str | None = None,
                 content: str | None = None, active: bool | None = None) -> dict | None:
    sets, params = ["updated_at = now()"], []
    if title is not None:
        sets.append("title = %s")
        params.append(title.strip())
    if content is not None:
        sets.append("content = %s")
        params.append(content.strip())
    if active is not None:
        sets.append("active = %s")
        params.append(active)
    conn = get_conn()
    try:
        row = conn.execute(
            f"""UPDATE agent_knowledge SET {', '.join(sets)}
                WHERE id = %s AND tenant_id = %s
                RETURNING id, title, content, active, updated_at""",
            (*params, entry_id, tenant_id)).fetchone()
        conn.commit()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_entry(tenant_id: str, entry_id: int) -> bool:
    conn = get_conn()
    try:
        cur = conn.execute(
            "DELETE FROM agent_knowledge WHERE id = %s AND tenant_id = %s",
            (entry_id, tenant_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def create_from_document(tenant_id: str, filename: str, content: bytes) -> dict:
    """Ingesta un documento (PDF/DOCX/TXT) como entrada de conocimiento:
    extrae su texto (mismo motor que usa el asistente para adjuntos) y lo
    guarda como una entrada. El agente lo usará como cualquier otra nota.
    Recorta el cuerpo a un tamaño manejable para el prompt."""
    from .files import extract_text, save_upload

    saved = save_upload(filename, content)
    text = (extract_text(saved["path"]) or "").strip()
    if not text:
        raise ValueError(
            "No se pudo extraer texto del documento (¿PDF escaneado o vacío?)")
    # El prompt no debe cargar un doc entero: se guarda un extracto amplio y se
    # recorta de nuevo al inyectar (MAX_CONTENT_CHARS).
    body = text[:8000]
    title = f"Documento: {filename}"
    return create_entry(tenant_id, title, body)


def knowledge_context(tenant_id: str) -> str:
    """Bloque de texto para el system prompt con el conocimiento activo del
    tenant. Cadena vacía si no hay entradas (o si la BD falla: el chat nunca
    debe romperse por esto)."""
    try:
        entries = list_entries(tenant_id, include_inactive=False)
    except psycopg.Error as exc:
        log.warning("knowledge_context falló (%s); se omite", exc)
        return ""
    if not entries:
        return ""
    lines = [
        "\n\nCONOCIMIENTO DEL NEGOCIO (actualizado por gerencia — tiene "
        "prioridad sobre cualquier dato memorizado; si contradice algo, "
        "gana esta sección):"
    ]
    for e in entries[:MAX_ENTRIES_IN_PROMPT]:
        content = e["content"][:MAX_CONTENT_CHARS]
        lines.append(f"- {e['title']}: {content}")
    return "\n".join(lines)
