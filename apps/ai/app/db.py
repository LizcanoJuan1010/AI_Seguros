"""PostgreSQL (esquema `seguria`): DDL, seeds (catálogo, FX, demo) y helpers de acceso.

Todo el data-layer del servicio IA vive en Postgres (psycopg 3, API sync). Las
tablas del dominio (Prisma) viven en `public`; las del asistente en un esquema
dedicado `seguria` para no chocar. El esquema se toma de `SEGURIA_DB_SCHEMA`
(default `seguria`) — los tests lo apuntan a un esquema aislado `seguria_test`.
La conexión se abre con `search_path` fijado a ese esquema, así todas las
consultas quedan sin cualificar y caen siempre en `seguria`.
"""
import csv
import json
import logging
import os
from datetime import datetime, timedelta

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from .config import DATA_DIR, resolve_database_url

# DDL portado de SQLite a PostgreSQL. Se crea SIN cualificar (va al search_path,
# que get_conn fija al esquema `seguria`). Cambios de dialecto respecto a SQLite:
#   AUTOINCREMENT           -> BIGINT GENERATED ALWAYS AS IDENTITY
#   REAL                    -> DOUBLE PRECISION
#   created_at TEXT + datetime('now') -> TIMESTAMPTZ DEFAULT now()
# Mismas tablas/columnas y claves: leads.phone UNIQUE, fx_rates PK(currency,date),
# chat_history PK(session_id,seq), checkout_session/intake_session PK(session_key).
SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    aseguradora TEXT NOT NULL,
    paises TEXT NOT NULL,            -- JSON array de códigos país
    suma_base_usd DOUBLE PRECISION NOT NULL,
    prima_base_usd DOUBLE PRECISION NOT NULL,
    prima_por_dia INTEGER DEFAULT 0,
    coberturas TEXT NOT NULL,        -- JSON array
    factores TEXT NOT NULL,          -- JSON object
    modalidad TEXT DEFAULT 'individual'  -- colectiva|individual|asesor, ver underwriting.py
);
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT NOT NULL,
    date TEXT NOT NULL,
    usd_rate DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (currency, date)
);
CREATE TABLE IF NOT EXISTS leads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phone TEXT UNIQUE,
    name TEXT,
    country TEXT,
    age INTEGER,
    stage TEXT DEFAULT 'nuevo',      -- nuevo|descubrimiento|cotizado|documento|cerrado|perdido
    source TEXT DEFAULT 'whatsapp',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- Puente hacia el Lead canónico de Prisma (motor de leads del backend): esta
-- tabla local sigue siendo la del cotizador (quotes.lead_id la referencia),
-- pero cada fila queda enlazada al Lead real que ve el CRM/scoring.
ALTER TABLE leads ADD COLUMN IF NOT EXISTS prisma_lead_id UUID;
CREATE TABLE IF NOT EXISTS quotes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lead_id BIGINT REFERENCES leads(id),
    product_id TEXT REFERENCES products(id),
    country TEXT NOT NULL,
    currency TEXT NOT NULL,
    sum_assured_usd DOUBLE PRECISION NOT NULL,
    premium_monthly_usd DOUBLE PRECISION NOT NULL,
    premium_monthly_local DOUBLE PRECISION NOT NULL,
    breakdown TEXT NOT NULL,         -- JSON con factores aplicados
    status TEXT DEFAULT 'emitida',   -- emitida|documento|aceptada|rechazada
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS conversations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    phone TEXT,
    role TEXT,                       -- cliente|asistente|gerente
    channel TEXT DEFAULT 'whatsapp', -- whatsapp|web|voz
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS checkout_session (
    session_key TEXT PRIMARY KEY,
    full_name TEXT,
    document_type TEXT DEFAULT 'CC',
    document_id TEXT,
    birth_date TEXT,
    email TEXT,
    phone TEXT,
    city TEXT,
    department TEXT,
    consent INTEGER DEFAULT 0,
    consent_at TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS intake_session (
    session_key TEXT PRIMARY KEY,
    datos TEXT DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS chat_history (
    session_id TEXT,
    seq INTEGER,
    message TEXT,
    PRIMARY KEY (session_id, seq)
);
-- Perfil (profiling.build_profile) más reciente por teléfono. 'llamada' lo
-- llena call_profiling.py tras cada llamada de ElevenLabs; 'mock' son
-- perfiles de prueba sembrados por mock_profiles.py (ver init_db).
CREATE TABLE IF NOT EXISTS customer_profile (
    phone TEXT PRIMARY KEY,
    perfil JSONB NOT NULL,
    fuente TEXT DEFAULT 'llamada',
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- Conocimiento del negocio editable por gerencia (panel "Agente IA" del CRM).
-- Las entradas activas se inyectan al system prompt de TODAS las
-- conversaciones del tenant (ver agent_core.run_agent / knowledge.py).
CREATE TABLE IF NOT EXISTS agent_knowledge (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT now()
);
-- true cuando gerencia editó el producto desde el CRM: el seed del catálogo
-- JSON deja de pisar esa fila en los siguientes arranques.
ALTER TABLE products ADD COLUMN IF NOT EXISTS editado_manual BOOLEAN DEFAULT FALSE;
"""

COUNTRY_CURRENCY = {
    "CO": "COP", "MX": "MXN", "PE": "PEN", "AR": "ARS", "CL": "CLP",
    "EC": "USD", "PA": "USD", "CR": "CRC", "DO": "DOP", "GT": "GTQ",
    "UY": "UYU", "SV": "USD",
}
COUNTRY_NAMES = {
    "CO": "Colombia", "MX": "México", "PE": "Perú", "AR": "Argentina",
    "CL": "Chile", "EC": "Ecuador", "PA": "Panamá", "CR": "Costa Rica",
    "DO": "Rep. Dominicana", "GT": "Guatemala", "UY": "Uruguay", "SV": "El Salvador",
}


def _dsn() -> str:
    """DSN de Postgres. Reusa DIRECT_URL/DATABASE_URL del backend; fallback local Docker."""
    return resolve_database_url() or "postgresql://seguria:seguria@localhost:5432/seguria"


def db_schema() -> str:
    """Esquema activo. `seguria` en producción; `seguria_test` en la suite."""
    return os.getenv("SEGURIA_DB_SCHEMA", "seguria")


def get_conn() -> psycopg.Connection:
    """Conexión psycopg 3 con filas como dict y `search_path` fijado al esquema.

    No es autocommit: las escrituras deben llamar `conn.commit()` (como en el
    código original). El `search_path` cae al esquema `seguria` (o el de test),
    así el DDL/consultas sin cualificar viven ahí y nunca en `public`.
    """
    schema = db_schema()
    return psycopg.connect(
        _dsn(), row_factory=dict_row,
        options=f"-c search_path={schema}", connect_timeout=10,
    )


def init_db(seed_demo: bool = True) -> None:
    schema = db_schema()
    conn = get_conn()
    try:
        conn.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        conn.execute(SCHEMA)  # sin cualificar → cae en el search_path (esquema seguria)
        # Migra instalaciones con la tabla `quotes` ya creada antes de este
        # campo (mismo criterio inline que kyc.py::_tables — CREATE TABLE IF
        # NOT EXISTS no altera una tabla que ya existía con otro shape).
        # Guarda el PDF de la cotización (generar_documento) para que el
        # checklist de activación pueda enlazarlo sin regenerarlo.
        conn.execute("ALTER TABLE quotes ADD COLUMN IF NOT EXISTS document_url TEXT")
        # Modalidad del producto (colectiva|individual|asesor — ver
        # underwriting.py y checklist.py): guaranteed-acceptance colectiva NO
        # pasa por biometría/underwriting individual; "asesor" no es
        # autogestionable en absoluto (Nota_estrategica_Seguros_Colsubsidio.pdf).
        conn.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS "
                    "modalidad TEXT DEFAULT 'individual'")
        _seed_catalog(conn)
        _seed_fx(conn)
        if seed_demo and conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"] == 0:
            _seed_demo(conn)
        if seed_demo and conn.execute(
                "SELECT COUNT(*) c FROM customer_profile").fetchone()["c"] == 0:
            from .mock_profiles import seed_mock_profiles
            seed_mock_profiles(conn)
        conn.commit()
        # Documentos firmados demo: idempotente (regenera archivos faltantes,
        # no duplica la referencia en la BD), fuera del guard de "primera vez"
        # porque los PDFs viven en un dir efímero del contenedor.
        if seed_demo:
            try:
                from .demo_documents import seed_demo_documents
                seed_demo_documents(conn)
            except Exception as exc:  # noqa: BLE001 - demo best-effort
                logging.getLogger("seguria.db").warning(
                    "seed_demo_documents falló: %s", exc)
    finally:
        conn.close()


def _seed_catalog(conn: psycopg.Connection) -> None:
    catalog = json.loads((DATA_DIR / "catalogo_productos.json").read_text(encoding="utf-8"))
    for p in catalog["productos"]:
        conn.execute(
            """INSERT INTO products
               (id, tipo, nombre, aseguradora, paises, suma_base_usd, prima_base_usd,
                prima_por_dia, coberturas, factores, modalidad)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO UPDATE SET
                 tipo=EXCLUDED.tipo, nombre=EXCLUDED.nombre, aseguradora=EXCLUDED.aseguradora,
                 paises=EXCLUDED.paises, suma_base_usd=EXCLUDED.suma_base_usd,
                 prima_base_usd=EXCLUDED.prima_base_usd, prima_por_dia=EXCLUDED.prima_por_dia,
                 coberturas=EXCLUDED.coberturas, factores=EXCLUDED.factores,
                 modalidad=EXCLUDED.modalidad
               WHERE products.editado_manual IS DISTINCT FROM TRUE""",
            (p["id"], p["tipo"], p["nombre"], p["aseguradora"], json.dumps(p["paises"]),
             p["suma_base_usd"], p["prima_base_usd"], int(p.get("prima_por_dia", False)),
             json.dumps(p["coberturas"], ensure_ascii=False),
             json.dumps(p["factores"], ensure_ascii=False),
             p.get("modalidad") or "individual"),
        )


def _seed_fx(conn: psycopg.Connection) -> None:
    fx_file = DATA_DIR / "fx_rates.csv"
    if not fx_file.exists():
        return
    with open(fx_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                """INSERT INTO fx_rates (currency, date, usd_rate) VALUES (%s,%s,%s)
                   ON CONFLICT (currency, date) DO UPDATE SET usd_rate=EXCLUDED.usd_rate""",
                (row["currency"], row["date"], float(row["usd_rate"])),
            )


def latest_fx(conn: psycopg.Connection, currency: str) -> float:
    """Última tasa moneda_local/USD conocida; 1.0 para USD."""
    if currency == "USD":
        return 1.0
    row = conn.execute(
        "SELECT usd_rate FROM fx_rates WHERE currency=%s ORDER BY date DESC LIMIT 1",
        (currency,),
    ).fetchone()
    return row["usd_rate"] if row else 1.0


def log_conversation(phone: str, role: str, message: str, channel: str = "whatsapp") -> None:
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO conversations (phone, role, channel, message) VALUES (%s,%s,%s,%s)",
            (phone, role, channel, message[:2000]),
        )
        conn.commit()
    finally:
        conn.close()


def _seed_demo(conn: psycopg.Connection) -> None:
    """Leads/cotizaciones de demostración para que el panel gerencial muestre datos."""
    import random
    random.seed(42)
    stages = ["nuevo", "descubrimiento", "cotizado", "cotizado", "documento", "cerrado", "cerrado", "perdido"]
    names = ["Ana Torres", "Luis Pérez", "María Gómez", "Carlos Ruiz", "Sofía Díaz",
             "Jorge Silva", "Lucía Mendez", "Pedro Rojas", "Valentina Cruz", "Diego Vargas",
             "Camila Herrera", "Andrés Castro", "Isabella Ortiz", "Miguel Ríos", "Paula Núñez"]
    countries = ["CO", "CO", "CO", "MX", "MX", "PE", "PA", "EC", "CR", "AR", "CL", "DO", "GT", "UY", "SV"]
    products = conn.execute("SELECT * FROM products").fetchall()
    now = datetime.utcnow()
    for i, (name, country) in enumerate(zip(names, countries)):
        created = now - timedelta(days=random.randint(0, 28), hours=random.randint(0, 23))
        stage = random.choice(stages)
        age = random.randint(22, 64)
        lead_id = conn.execute(
            "INSERT INTO leads (phone, name, country, age, stage, created_at, updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (f"+57300555{1000+i}", name, country, age, stage, created, created),
        ).fetchone()["id"]
        if stage in ("cotizado", "documento", "cerrado", "perdido"):
            eligible = [p for p in products if country in json.loads(p["paises"])]
            for p in random.sample(eligible, k=min(len(eligible), random.randint(1, 2))):
                factor = random.uniform(0.8, 2.2)
                usd = round(p["prima_base_usd"] * factor, 2)
                currency = COUNTRY_CURRENCY[country]
                rate = latest_fx(conn, currency)
                conn.execute(
                    """INSERT INTO quotes (lead_id, product_id, country, currency, sum_assured_usd,
                       premium_monthly_usd, premium_monthly_local, breakdown, status, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (lead_id, p["id"], country, currency, p["suma_base_usd"],
                     usd, round(usd * rate, 2), json.dumps({"demo": True, "factor": round(factor, 2)}),
                     "aceptada" if stage == "cerrado" else "emitida", created),
                )
