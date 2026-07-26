"""Fixtures de pytest: corre la suite contra la Postgres de compose en un esquema
AISLADO (`seguria_test`) que se crea al inicio y se DROPa (CASCADE) al final, para
no ensuciar el esquema real `seguria`.

Cómo correr los tests contra Postgres (compose en localhost:5432):

    DATABASE_URL=postgresql://seguria:seguria@localhost:5432/seguria \\
        .venv/bin/python -m pytest tests/ -q

Si Postgres no está disponible, TODOS los tests se SALTAN con un motivo claro
(no fallan); la línea de arriba explica cómo levantarlos.
"""
import os

import pytest

# Debe fijarse ANTES de importar `app.*`: config y db leen estas variables.
# El esquema de test se lee en get_conn() vía `SEGURIA_DB_SCHEMA`.
os.environ.setdefault("SEGURIA_DB_SCHEMA", "seguria_test")
os.environ.setdefault("MANAGER_API_KEY", "test-mgr")
os.environ.setdefault("SERVICE_API_KEY", "test-svc")
os.environ.setdefault("DATABASE_URL", "postgresql://seguria:seguria@localhost:5432/seguria")

TEST_SCHEMA = os.environ["SEGURIA_DB_SCHEMA"]
_DSN = os.environ["DATABASE_URL"]
_RUN_HINT = (f"DATABASE_URL={_DSN} .venv/bin/python -m pytest tests/ -q")


def _pg_available() -> tuple[bool, str]:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        return False, f"psycopg no instalado ({exc})"
    try:
        with psycopg.connect(_DSN, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True, ""
    except Exception as exc:
        return False, f"Postgres no disponible en {_DSN} ({exc})"


_PG_OK, _PG_REASON = _pg_available()


def pytest_collection_modifyitems(config, items):
    """Sin Postgres: salta tests de integración; los marcados `unit` sí corren."""
    if _PG_OK:
        return
    skip = pytest.mark.skip(reason=f"{_PG_REASON}. Córrelos con: {_RUN_HINT}")
    for item in items:
        if "unit" in item.keywords:
            continue
        item.add_marker(skip)


@pytest.fixture(scope="session", autouse=True)
def _seguria_test_schema():
    """Crea `seguria_test` limpio + esquema/seeds; lo DROPa (CASCADE) al terminar."""
    if not _PG_OK:
        yield
        return
    import psycopg
    from psycopg import sql

    ident = sql.Identifier(TEST_SCHEMA)
    with psycopg.connect(_DSN, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(ident))
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(ident))

    from app.db import init_db
    init_db()  # crea tablas + seeds (catálogo, FX, demo) dentro del esquema de test

    yield

    with psycopg.connect(_DSN, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(ident))
