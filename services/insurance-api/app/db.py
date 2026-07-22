"""SQLite: esquema, seeds (catálogo, FX, demo) y helpers de acceso."""
import csv
import json
import sqlite3
from datetime import datetime, timedelta

from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    tipo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    aseguradora TEXT NOT NULL,
    paises TEXT NOT NULL,            -- JSON array de códigos país
    suma_base_usd REAL NOT NULL,
    prima_base_usd REAL NOT NULL,
    prima_por_dia INTEGER DEFAULT 0,
    coberturas TEXT NOT NULL,        -- JSON array
    factores TEXT NOT NULL           -- JSON object
);
CREATE TABLE IF NOT EXISTS fx_rates (
    currency TEXT NOT NULL,
    date TEXT NOT NULL,
    usd_rate REAL NOT NULL,
    PRIMARY KEY (currency, date)
);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT UNIQUE,
    name TEXT,
    country TEXT,
    age INTEGER,
    stage TEXT DEFAULT 'nuevo',      -- nuevo|descubrimiento|cotizado|documento|cerrado|perdido
    source TEXT DEFAULT 'whatsapp',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    product_id TEXT REFERENCES products(id),
    country TEXT NOT NULL,
    currency TEXT NOT NULL,
    sum_assured_usd REAL NOT NULL,
    premium_monthly_usd REAL NOT NULL,
    premium_monthly_local REAL NOT NULL,
    breakdown TEXT NOT NULL,         -- JSON con factores aplicados
    status TEXT DEFAULT 'emitida',   -- emitida|documento|aceptada|rechazada
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT,
    role TEXT,                       -- cliente|asistente|gerente
    channel TEXT DEFAULT 'whatsapp', -- whatsapp|web|voz
    message TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
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


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")   # lectores no bloquean al escritor
    conn.execute("PRAGMA busy_timeout = 5000")  # reintenta ante lock antes de fallar
    return conn


def init_db(seed_demo: bool = True) -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    _seed_catalog(conn)
    _seed_fx(conn)
    if seed_demo and conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"] == 0:
        _seed_demo(conn)
    conn.commit()
    conn.close()


def _seed_catalog(conn: sqlite3.Connection) -> None:
    catalog = json.loads((DATA_DIR / "catalogo_productos.json").read_text(encoding="utf-8"))
    for p in catalog["productos"]:
        conn.execute(
            """INSERT OR REPLACE INTO products
               (id, tipo, nombre, aseguradora, paises, suma_base_usd, prima_base_usd,
                prima_por_dia, coberturas, factores)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (p["id"], p["tipo"], p["nombre"], p["aseguradora"], json.dumps(p["paises"]),
             p["suma_base_usd"], p["prima_base_usd"], int(p.get("prima_por_dia", False)),
             json.dumps(p["coberturas"], ensure_ascii=False),
             json.dumps(p["factores"], ensure_ascii=False)),
        )


def _seed_fx(conn: sqlite3.Connection) -> None:
    fx_file = DATA_DIR / "fx_rates.csv"
    if not fx_file.exists():
        return
    with open(fx_file, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                "INSERT OR REPLACE INTO fx_rates (currency, date, usd_rate) VALUES (?,?,?)",
                (row["currency"], row["date"], float(row["usd_rate"])),
            )


def latest_fx(conn: sqlite3.Connection, currency: str) -> float:
    """Última tasa moneda_local/USD conocida; 1.0 para USD."""
    if currency == "USD":
        return 1.0
    row = conn.execute(
        "SELECT usd_rate FROM fx_rates WHERE currency=? ORDER BY date DESC LIMIT 1",
        (currency,),
    ).fetchone()
    return row["usd_rate"] if row else 1.0


def log_conversation(phone: str, role: str, message: str, channel: str = "whatsapp") -> None:
    conn = get_conn()
    conn.execute(
        "INSERT INTO conversations (phone, role, channel, message) VALUES (?,?,?,?)",
        (phone, role, channel, message[:2000]),
    )
    conn.commit()
    conn.close()


def _seed_demo(conn: sqlite3.Connection) -> None:
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
        created = (now - timedelta(days=random.randint(0, 28), hours=random.randint(0, 23))).strftime("%Y-%m-%d %H:%M:%S")
        stage = random.choice(stages)
        age = random.randint(22, 64)
        cur = conn.execute(
            "INSERT INTO leads (phone, name, country, age, stage, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (f"+57300555{1000+i}", name, country, age, stage, created, created),
        )
        lead_id = cur.lastrowid
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
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (lead_id, p["id"], country, currency, p["suma_base_usd"],
                     usd, round(usd * rate, 2), json.dumps({"demo": True, "factor": round(factor, 2)}),
                     "aceptada" if stage == "cerrado" else "emitida", created),
                )
