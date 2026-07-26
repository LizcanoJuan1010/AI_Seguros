"""Memoria multi-tenant persistente (patrón Paloma), partición dura `(tenant_id, user_id)`.

Capa async sobre Postgres (asyncpg). La clave de partición es el par
`(tenant_id, user_id)`: `tenant_id` es la organización (Team) y `user_id` es el
cliente final (teléfono del cliente o `web:{session_id}`). Cada par es un
compartimento aislado: NUNCA se cruzan datos entre tenants ni entre usuarios —
todas las consultas filtran por `tenant_id` Y `user_id`.

DEGRADACIÓN GRACIOSA: si falta `DATABASE_URL`, no está `asyncpg`, o Postgres no
responde, la memoria cae a un dict en proceso (también particionado por el par).
El arranque nunca se rompe por esto.
"""
import hashlib
import logging
from datetime import datetime, timezone

from . import config

try:  # asyncpg es opcional: sin él, la memoria vive en un dict en proceso
    import asyncpg
except ImportError:  # pragma: no cover - depende del entorno
    asyncpg = None

log = logging.getLogger("seguria.memory")

MAX_PER_USER = 50  # tope de recuerdos por `(tenant_id, user_id)` (se recorta al insertar)

DEFAULT_TENANT = "demo"  # fallback de partición (los endpoints inyectan el tenant real)

# La tabla `memory` vive en el esquema dedicado `seguria` (mismo esquema que el resto
# del data-layer del servicio IA; las tablas del dominio Prisma están en `public`).
# Esquema base: tabla sin la UNIQUE inline (la crea la migración idempotente, con nombre
# estable, para que ON CONFLICT (tenant_id, user_id, hash) tenga índice de respaldo).
CREATE_SQL = """
CREATE SCHEMA IF NOT EXISTS seguria;
CREATE TABLE IF NOT EXISTS seguria.memory (
  id BIGSERIAL PRIMARY KEY, tenant_id TEXT NOT NULL DEFAULT 'demo',
  user_id TEXT NOT NULL, content TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT 'general', hash TEXT NOT NULL,
  score INT NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
"""

# Migración idempotente a la partición de dos ejes `(tenant_id, user_id)`. Como la
# tabla pudo crearse antes SIN `tenant_id` y con `UNIQUE(user_id, hash)`, aquí:
#  1) añadimos la columna tenant_id (default 'demo' para las filas demo ya presentes),
#  2) soltamos la unique/índice viejos por eje único,
#  3) creamos la unique `(tenant_id, user_id, hash)` y el índice de ranking por par.
MIGRATE_SQL = """
ALTER TABLE seguria.memory ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'demo';
ALTER TABLE seguria.memory DROP CONSTRAINT IF EXISTS memory_user_id_hash_key;
DROP INDEX IF EXISTS seguria.memory_user_rank;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'memory_tenant_user_hash_key'
      AND conrelid = 'seguria.memory'::regclass
  ) THEN
    ALTER TABLE seguria.memory
      ADD CONSTRAINT memory_tenant_user_hash_key UNIQUE (tenant_id, user_id, hash);
  END IF;
END $$;
CREATE INDEX IF NOT EXISTS memory_tenant_user_rank
  ON seguria.memory (tenant_id, user_id, score DESC, updated_at DESC);
"""

# Estado del módulo (se puebla en el lifespan de FastAPI vía init_pool()).
_pool: "asyncpg.Pool | None" = None
_use_pg = False
# Fallback en proceso: (tenant_id, user_id) -> {hash: {content, category, score, updated_at}}
_fallback: dict[tuple[str, str], dict[str, dict]] = {}


def _hash(content: str) -> str:
    """Dedup determinista: md5 del contenido en minúsculas, 12 hex."""
    return hashlib.md5(content.lower().encode("utf-8")).hexdigest()[:12]


# ---------- Ciclo de vida del pool ----------

async def init_pool() -> None:
    """Crea el pool asyncpg y la tabla. Si algo falla, activa el modo dict."""
    global _pool, _use_pg
    if asyncpg is None or not config.DATABASE_URL:
        log.info("memoria en modo dict (sin asyncpg o sin DATABASE_URL)")
        return
    try:
        _pool = await asyncpg.create_pool(
            config.DATABASE_URL, min_size=1, max_size=5,
            timeout=10, command_timeout=10, statement_cache_size=0)
        async with _pool.acquire() as conn:
            await conn.execute(CREATE_SQL)
            await conn.execute(MIGRATE_SQL)  # partición dura (tenant_id, user_id), idempotente
        _use_pg = True
        log.info("memoria Postgres lista (partición tenant_id, user_id)")
    except Exception as exc:  # Postgres caído no debe tumbar el arranque
        log.warning("Postgres no disponible (%s); memoria en modo dict", exc)
        _pool = None
        _use_pg = False


async def close_pool() -> None:
    global _pool, _use_pg
    if _pool is not None:
        try:
            await _pool.close()
        except Exception:  # pragma: no cover
            log.debug("error cerrando el pool", exc_info=True)
    _pool = None
    _use_pg = False


def using_postgres() -> bool:
    return _use_pg and _pool is not None


# ---------- API async ----------

async def add_memory(user_id: str, content: str, category: str = "general",
                     *, tenant_id: str = DEFAULT_TENANT) -> None:
    """Guarda un recuerdo bajo la partición `(tenant_id, user_id)`. Dedup por hash
    (score++ si ya existe); recorta a 50 por par tenant/usuario."""
    content = (content or "").strip()
    tenant_id = tenant_id or DEFAULT_TENANT
    if not user_id or not content:
        return
    h = _hash(content)
    if using_postgres():
        try:
            async with _pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO seguria.memory (tenant_id, user_id, content, category, hash)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (tenant_id, user_id, hash)
                       DO UPDATE SET score = memory.score + 1, updated_at = now()""",
                    tenant_id, user_id, content, category, h)
                await conn.execute(
                    """DELETE FROM seguria.memory
                        WHERE tenant_id = $1 AND user_id = $2 AND id NOT IN (
                          SELECT id FROM seguria.memory WHERE tenant_id = $1 AND user_id = $2
                          ORDER BY score DESC, updated_at DESC LIMIT $3)""",
                    tenant_id, user_id, MAX_PER_USER)
            return
        except Exception as exc:  # falla puntual → cae al dict sin romper el turno
            log.warning("add_memory Postgres falló (%s); usando dict", exc)
    bucket = _fallback.setdefault((tenant_id, user_id), {})
    now = datetime.now(timezone.utc)
    if h in bucket:
        bucket[h]["score"] += 1
        bucket[h]["updated_at"] = now
    else:
        bucket[h] = {"content": content, "category": category, "score": 1, "updated_at": now}
    if len(bucket) > MAX_PER_USER:
        top = sorted(bucket.items(),
                     key=lambda kv: (kv[1]["score"], kv[1]["updated_at"]),
                     reverse=True)[:MAX_PER_USER]
        _fallback[(tenant_id, user_id)] = dict(top)


async def get_memory_context(user_id: str, limit: int = 20,
                             *, tenant_id: str = DEFAULT_TENANT) -> str:
    """Bloque de texto con los recuerdos más relevantes del par `(tenant_id, user_id)`
    (score, luego recencia)."""
    tenant_id = tenant_id or DEFAULT_TENANT
    if not user_id:
        return ""
    rows: list[tuple[str, str]] = []
    if using_postgres():
        try:
            async with _pool.acquire() as conn:
                recs = await conn.fetch(
                    """SELECT content, category FROM seguria.memory
                        WHERE tenant_id = $1 AND user_id = $2
                        ORDER BY score DESC, updated_at DESC LIMIT $3""",
                    tenant_id, user_id, limit)
            rows = [(r["content"], r["category"]) for r in recs]
        except Exception as exc:
            log.warning("get_memory_context Postgres falló (%s)", exc)
            rows = []
    if not rows:
        bucket = _fallback.get((tenant_id, user_id), {})
        items = sorted(bucket.values(),
                       key=lambda v: (v["score"], v["updated_at"]),
                       reverse=True)[:limit]
        rows = [(v["content"], v["category"]) for v in items]
    if not rows:
        return ""
    lines = "\n".join(f"- ({cat}) {content}" for content, cat in rows)
    return ("MEMORIA DEL CLIENTE (contexto de turnos anteriores, úsalo con naturalidad; "
            "no lo recites literalmente):\n" + lines)


async def search_memories(user_id: str, query: str, limit: int = 3,
                          *, tenant_id: str = DEFAULT_TENANT) -> list[str]:
    """Recuerdos relevantes a `query`. SIEMPRE acotado por `(tenant_id, user_id)`.

    En Postgres usa full-text en español y cae a ILIKE si el tsquery no da hits.
    """
    tenant_id = tenant_id or DEFAULT_TENANT
    if not user_id or not query:
        return []
    q = query.strip()
    if using_postgres():
        try:
            async with _pool.acquire() as conn:
                recs = await conn.fetch(
                    """SELECT content FROM seguria.memory
                         WHERE tenant_id = $1 AND user_id = $2
                           AND to_tsvector('spanish', content)
                               @@ plainto_tsquery('spanish', $3)
                       ORDER BY score DESC, updated_at DESC LIMIT $4""",
                    tenant_id, user_id, q, limit)
                if not recs:
                    recs = await conn.fetch(
                        """SELECT content FROM seguria.memory
                             WHERE tenant_id = $1 AND user_id = $2
                               AND content ILIKE '%' || $3 || '%'
                           ORDER BY score DESC, updated_at DESC LIMIT $4""",
                        tenant_id, user_id, q, limit)
            return [r["content"] for r in recs]
        except Exception as exc:
            log.warning("search_memories Postgres falló (%s)", exc)
    bucket = _fallback.get((tenant_id, user_id), {})
    ql = q.lower()
    hits = [v for v in bucket.values() if ql in v["content"].lower()]
    hits.sort(key=lambda v: (v["score"], v["updated_at"]), reverse=True)
    return [v["content"] for v in hits[:limit]]
