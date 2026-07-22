"""SegurIA API — catálogo, cotizador, leads, documentos e insights.

Consumida por las skills del agente Hermes (vía HTTP) y por la SPA (chat + panel gerencial).
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import insights as insights_mod
from .config import CORS_ORIGINS, MANAGER_API_KEY, MANAGER_PHONES, SERVICE_API_KEY
from .db import COUNTRY_NAMES, get_conn, init_db, log_conversation
from .documents import build_quote_pdf
from .metabase_client import MetabaseClient
from .quoting import quote_product, recommend


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SegurIA API", version="0.1.0", lifespan=lifespan,
              description="Backend del asistente de venta de seguros LATAM")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS or [],
                   allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador estable de la conversación")
    message: str
    phone: str | None = Field(None, description="WhatsApp del cliente si se conoce")
    manager_key: str | None = Field(None, description="API key para actuar con rol gerente")


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Turno conversacional del agente (function calling multi-ronda con DeepSeek)."""
    from .agent_core import run_agent
    role = "gerente" if req.manager_key == MANAGER_API_KEY else "cliente"
    log_conversation(req.phone or f"web:{req.session_id}", role, req.message, channel="web")
    result = run_agent(req.session_id, req.message, phone=req.phone or "", role=role)
    if result.get("reply"):
        log_conversation(req.phone or f"web:{req.session_id}", "asistente",
                         result["reply"], channel="web")
    return result


def require_manager(x_api_key: str = Header(default="")) -> None:
    if x_api_key != MANAGER_API_KEY:
        raise HTTPException(403, "Se requiere API key de gerente (header X-API-Key)")


def require_service(x_api_key: str = Header(default=""),
                    x_service_key: str = Header(default="")) -> None:
    """Endpoints internos que tocan PII: los consume el agente/backend, no el
    cliente final. Acepta la key de servicio o la de gerente."""
    if x_service_key != SERVICE_API_KEY and x_api_key != MANAGER_API_KEY:
        raise HTTPException(403, "Se requiere API key de servicio (header X-Service-Key)")


# ---------- Modelos ----------

class QuoteRequest(BaseModel):
    country: str = Field(..., description="Código ISO-2 del país, ej. CO")
    tipo: str | None = Field(None, description="vida|salud|auto|hogar|viaje|pyme|accidentes")
    age: int | None = None
    sum_assured_usd: float | None = None
    budget_monthly_usd: float | None = None
    phone: str | None = Field(None, description="WhatsApp del cliente para registrar el lead")
    name: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict,
                                   description="fumador, dependientes, valor_bien_usd, dias_viaje, zona_alto_riesgo...")


class LeadUpdate(BaseModel):
    phone: str
    name: str | None = None
    country: str | None = None
    age: int | None = None
    stage: str | None = None


class ConversationLog(BaseModel):
    phone: str
    role: str = "cliente"
    channel: str = "whatsapp"
    message: str


# ---------- Catálogo ----------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "seguria-api"}


@app.get("/api/countries")
def countries() -> list[dict]:
    return [{"code": c, "nombre": n} for c, n in COUNTRY_NAMES.items()]


@app.get("/api/products")
def products(country: str | None = None, tipo: str | None = None) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    out = []
    for r in rows:
        paises = json.loads(r["paises"])
        if country and country.upper() not in paises:
            continue
        if tipo and r["tipo"] != tipo:
            continue
        out.append({
            "id": r["id"], "tipo": r["tipo"], "nombre": r["nombre"],
            "aseguradora": r["aseguradora"], "paises": paises,
            "suma_base_usd": r["suma_base_usd"], "prima_base_usd": r["prima_base_usd"],
            "coberturas": json.loads(r["coberturas"]),
        })
    return out


# ---------- Cotización + leads ----------

def _upsert_lead(conn, phone: str | None, name: str | None, country: str,
                 age: int | None, stage: str) -> int | None:
    if not phone:
        return None
    row = conn.execute("SELECT id, stage FROM leads WHERE phone=?", (phone,)).fetchone()
    if row:
        conn.execute(
            """UPDATE leads SET name=COALESCE(?,name), country=?, age=COALESCE(?,age),
               stage=?, updated_at=datetime('now') WHERE id=?""",
            (name, country, age, stage, row["id"]))
        return row["id"]
    cur = conn.execute(
        "INSERT INTO leads (phone, name, country, age, stage) VALUES (?,?,?,?,?)",
        (phone, name, country, age, stage))
    return cur.lastrowid


@app.post("/api/quotes")
def create_quotes(req: QuoteRequest) -> dict:
    """Cotiza y devuelve hasta 3 opciones a la medida; registra lead y cotizaciones."""
    conn = get_conn()
    country = req.country.upper()
    if country not in COUNTRY_NAMES:
        conn.close()
        raise HTTPException(400, f"País no soportado: {country}. Usa uno de {list(COUNTRY_NAMES)}")
    options = recommend(conn, country=country, tipo=req.tipo, age=req.age,
                        sum_assured_usd=req.sum_assured_usd,
                        budget_monthly_usd=req.budget_monthly_usd, extras=req.extras)
    lead_id = _upsert_lead(conn, req.phone, req.name, country, req.age,
                           stage="cotizado" if options else "descubrimiento")
    quote_ids = []
    for o in options:
        cur = conn.execute(
            """INSERT INTO quotes (lead_id, product_id, country, currency, sum_assured_usd,
               premium_monthly_usd, premium_monthly_local, breakdown)
               VALUES (?,?,?,?,?,?,?,?)""",
            (lead_id, o["product_id"], country, o["moneda"], o["suma_asegurada_usd"],
             o["prima_mensual_usd"], o["prima_mensual_local"],
             json.dumps(o["breakdown"], ensure_ascii=False)))
        o["quote_id"] = cur.lastrowid
        quote_ids.append(cur.lastrowid)
    conn.commit()
    conn.close()
    return {"lead_id": lead_id, "opciones": options,
            "mensaje": None if options else
            "No hay productos de ese tipo en ese país; sugiere el tipo más cercano del catálogo."}


@app.post("/api/quotes/{quote_id}/document")
def quote_document(quote_id: int) -> dict:
    """Genera el PDF formal de una cotización emitida."""
    conn = get_conn()
    q = conn.execute(
        """SELECT q.*, p.nombre producto, p.tipo, p.aseguradora, p.coberturas, p.prima_por_dia
           FROM quotes q JOIN products p ON p.id=q.product_id WHERE q.id=?""",
        (quote_id,)).fetchone()
    if not q:
        conn.close()
        raise HTTPException(404, "Cotización no encontrada")
    lead = None
    if q["lead_id"]:
        lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (q["lead_id"],)).fetchone() or {})
        conn.execute("UPDATE leads SET stage='documento', updated_at=datetime('now') "
                     "WHERE id=? AND stage NOT IN ('cerrado','perdido')", (q["lead_id"],))
    conn.execute("UPDATE quotes SET status='documento' WHERE id=?", (quote_id,))
    quote_dict = {
        "product_id": q["product_id"], "producto": q["producto"], "tipo": q["tipo"],
        "aseguradora": q["aseguradora"], "pais": COUNTRY_NAMES.get(q["country"], q["country"]),
        "moneda": q["currency"], "suma_asegurada_usd": q["sum_assured_usd"],
        "prima_mensual_usd": q["premium_monthly_usd"],
        "prima_mensual_local": q["premium_monthly_local"],
        "tasa_fx": (q["premium_monthly_local"] / q["premium_monthly_usd"]) if q["premium_monthly_usd"] else 1.0,
        "coberturas": json.loads(q["coberturas"]),
        "periodicidad": "por viaje" if q["prima_por_dia"] else "mensual",
    }
    path = build_quote_pdf(quote_dict, lead)
    conn.commit()
    conn.close()
    return {"file_path": path, "download_url": f"/api/documents/{Path(path).name}"}


@app.get("/api/documents/{filename}")
def download_document(filename: str) -> FileResponse:
    from .config import DOCS_DIR
    path = (DOCS_DIR / filename).resolve()
    if not path.is_file() or path.parent != DOCS_DIR.resolve():
        raise HTTPException(404, "Documento no encontrado")
    return FileResponse(path, media_type="application/pdf", filename=filename)


@app.post("/api/leads", dependencies=[Depends(require_service)])
def update_lead(req: LeadUpdate) -> dict:
    conn = get_conn()
    lead_id = _upsert_lead(conn, req.phone, req.name, (req.country or "CO").upper(),
                           req.age, req.stage or "descubrimiento")
    conn.commit()
    conn.close()
    return {"lead_id": lead_id, "ok": True}


@app.post("/api/conversations", dependencies=[Depends(require_service)])
def log_message(req: ConversationLog) -> dict:
    log_conversation(req.phone, req.role, req.message, req.channel)
    return {"ok": True}


@app.get("/api/roles/{phone}", dependencies=[Depends(require_service)])
def role_for_phone(phone: str) -> dict:
    """La skill de Hermes consulta aquí si el número es de un gerente."""
    normalized = phone.replace(" ", "")
    return {"phone": normalized,
            "role": "gerente" if normalized in MANAGER_PHONES else "cliente"}


# ---------- Insights (solo gerentes) ----------

@app.get("/api/insights/summary", dependencies=[Depends(require_manager)])
def insights_summary() -> dict:
    conn = get_conn()
    data = insights_mod.summary(conn)
    conn.close()
    mb = MetabaseClient()
    data["metabase"] = {"enabled": mb.enabled}
    if mb.enabled:
        try:
            data["metabase"]["dashboards"] = mb.list_dashboards()
        except Exception as exc:  # Metabase caído no debe tumbar los insights locales
            data["metabase"]["error"] = str(exc)
    return data


@app.get("/api/proactive", dependencies=[Depends(require_manager)])
def proactive_all() -> dict:
    """Sugerencias de seguimiento (todos los clientes) + alertas de negocio."""
    from .proactive import client_nudges, manager_alerts
    conn = get_conn()
    data = {"nudges_clientes": client_nudges(conn), "alertas_gerente": manager_alerts(conn)}
    conn.close()
    return data


@app.get("/api/proactive/{phone}", dependencies=[Depends(require_service)])
def proactive_for_phone(phone: str) -> dict:
    """Sugerencias de seguimiento para un cliente puntual (lo usa la skill cron)."""
    from .proactive import client_nudges
    conn = get_conn()
    data = {"nudges": client_nudges(conn, phone)}
    conn.close()
    return data


@app.get("/api/insights/leads", dependencies=[Depends(require_manager)])
def insights_leads() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT l.*, COUNT(q.id) cotizaciones,
                  ROUND(COALESCE(SUM(q.premium_monthly_usd),0),2) prima_usd
           FROM leads l LEFT JOIN quotes q ON q.lead_id=l.id
           GROUP BY l.id ORDER BY l.updated_at DESC LIMIT 100""").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- SPA ----------

static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")
