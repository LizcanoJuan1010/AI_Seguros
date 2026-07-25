"""Acceso Postgres al schema `docket` — puerto de `services/pipeline/db.py` +
los INSERTs de `seed_versions.py`/`server.py` de docket-motor a psycopg 3.

Reusa `app.db.get_conn()` para la conexión (misma base, mismo DSN ya resuelto
por `config.py`) — el `search_path` de esa conexión apunta a `seguria`, pero
acá TODO SQL va `docket.`-prefijado explícito: nunca depender de search_path
(ese fue justo el bug ya resuelto una vez entre `public` y `seguria`, no
repetirlo con un tercer schema).
"""
import json
import logging

from .. import db as _db

log = logging.getLogger("seguria.docket_engine")


def conn():
    return _db.get_conn()


def get_or_create_campaign(c, client_slug: str) -> str:
    row = c.execute(
        "SELECT id FROM docket.campaigns WHERE client_slug = %s", (client_slug,)
    ).fetchone()
    if row:
        return str(row["id"])
    row = c.execute(
        "INSERT INTO docket.campaigns (client_slug) VALUES (%s) RETURNING id",
        (client_slug,),
    ).fetchone()
    return str(row["id"])


def insert_call(c, campaign_slug: str, external_id: str, transcript: str,
                turns: list[dict]) -> str | None:
    """Registra una conversación real como fila `docket.calls`. `turns` debe
    traer `role` ('agent'|'customer') y `text` por turno — el shape que
    `cluster.py` espera leer de `raw_meta->'turns'`. Idempotente por
    (campaign_id, source_file, external_id): reintentos no duplican."""
    campaign_id = get_or_create_campaign(c, campaign_slug)
    try:
        row = c.execute(
            """INSERT INTO docket.calls
                   (campaign_id, external_id, source_file, source_type, transcript, raw_meta)
               VALUES (%s, %s, 'app_sync', 'app_sync', %s, %s)
               ON CONFLICT (campaign_id, source_file, external_id) DO NOTHING
               RETURNING id""",
            (campaign_id, external_id, transcript,
             json.dumps({"turns": turns}, ensure_ascii=False)),
        ).fetchone()
        return str(row["id"]) if row else None
    except Exception:
        log.exception("no se pudo registrar en docket.calls (campaña=%s)", campaign_slug)
        return None


def latest_prompt_text(c, campaign_slug: str) -> str | None:
    """Texto de la versión más reciente (mayor version_number) de la campaña,
    o None si no hay ninguna sembrada todavía."""
    row = c.execute(
        """SELECT v.prompt_text FROM docket.versions v
           JOIN docket.campaigns camp ON camp.id = v.campaign_id
           WHERE camp.client_slug = %s
           ORDER BY v.version_number DESC LIMIT 1""",
        (campaign_slug,),
    ).fetchone()
    return row["prompt_text"] if row else None
