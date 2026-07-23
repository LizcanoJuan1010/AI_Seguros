"""SegurIA API — catálogo, cotizador, leads, documentos e insights.

Consumida por las skills del agente Hermes (vía HTTP) y por la SPA (chat + panel gerencial).
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import insights as insights_mod
from . import memory
from .assistant import router as assistant_router
from .embedded import router as embedded_router
from .auth import resolve_identity
from .config import (CORS_ORIGINS, MANAGER_API_KEY, MANAGER_PHONES,
                     SERVICE_API_KEY)
from .db import COUNTRY_NAMES, get_conn, init_db, log_conversation
from .documents import build_quote_pdf
from .metabase_client import MetabaseClient
from .quoting import quote_product, recommend


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await memory.init_pool()  # Postgres si está disponible; si no, memoria en dict
    # Informes periódicos por correo (patrón Paloma): loop en segundo plano.
    from . import reports as reports_mod
    import asyncio as _asyncio
    reports_task = _asyncio.create_task(reports_mod.scheduler_loop())
    try:
        yield
    finally:
        reports_task.cancel()
        await memory.close_pool()


app = FastAPI(title="SegurIA API", version="0.1.0", lifespan=lifespan,
              description="Backend del asistente de venta de seguros LATAM")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS or [],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(assistant_router)  # POST /api/assistant/chat/stream (SSE)
app.include_router(embedded_router)   # /api/embedded/* (quote & bind para aliados)


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador estable de la conversación")
    message: str
    phone: str | None = Field(None, description="WhatsApp del cliente si se conoce")
    manager_key: str | None = Field(None, description="API key para actuar con rol gerente")


@app.post("/api/chat")
def chat(req: ChatRequest,
         authorization: str = Header(default=""),
         x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> dict:
    """Turno conversacional del agente (function calling multi-ronda con DeepSeek).

    El tenant y el rol salen del JWT del login (`Authorization: Bearer <access>`):
    `tenant_id = claims.teamId`, `role` según `claims.role`. Si no hay token válido
    cae al header `X-Tenant-Id`/tenant demo y a `manager_key`. El estado se
    particiona por `(tenant_id, user_id)`."""
    from .agent_core import run_agent
    tenant_id, role = resolve_identity(authorization, x_tenant_id, req.manager_key)
    log_conversation(req.phone or f"web:{req.session_id}", role, req.message, channel="web")
    result = run_agent(req.session_id, req.message, phone=req.phone or "", role=role,
                       tenant_id=tenant_id)
    if result.get("reply"):
        log_conversation(req.phone or f"web:{req.session_id}", "asistente",
                         result["reply"], channel="web")
    return result


@app.get("/api/intake/requisitos/{tipo}")
def intake_requisitos(tipo: str) -> dict:
    """Formulario/campos reales requeridos para un tipo de seguro (KYC/SARLAFT/underwriting)."""
    from . import intake
    return intake.spec_formulario(tipo)


@app.post("/api/assistant/upload")
async def assistant_upload(file: UploadFile = File(...), session_id: str = "", phone: str = "") -> dict:
    """El cliente sube un documento (cédula, tarjeta de propiedad, RUT...); se guarda y
    queda disponible para que el agente lo lea con la herramienta analizar_documento."""
    try:
        from . import files as files_mod
    except Exception as exc:
        raise HTTPException(503, f"Lectura de archivos no disponible: {exc}")
    content = await file.read()
    saved = files_mod.save_upload(file.filename or "documento", content)
    # lectura inmediata (best-effort) para dar feedback al cliente
    parsed = files_mod.parse_document(saved["path"], file.filename or "")
    return {"file_id": saved["file_id"], "filename": saved.get("filename"),
            "tipo_detectado": parsed.get("tipo_detectado"),
            "campos_extraidos": parsed.get("campos_extraidos", {}),
            "resumen": parsed.get("resumen")}


# ---------- Voz: TTS de la respuesta (proxy al Kokoro del perfil `voz`) ----------

@app.get("/api/assistant/tts")
def assistant_tts(text: str) -> Response:
    """Convierte texto de respuesta en audio (mp3). Proxy al contenedor Kokoro
    para no exponerlo al navegador; sin el perfil `voz` responde 503 limpio."""
    clean = (text or "").strip()
    if not clean:
        raise HTTPException(400, "texto vacío")
    from .config import TTS_URL, TTS_VOICE
    try:
        import requests
        r = requests.post(f"{TTS_URL}/v1/audio/speech",
                          json={"model": "kokoro", "voice": TTS_VOICE,
                                "input": clean[:600], "response_format": "mp3"},
                          timeout=30)
        r.raise_for_status()
    except Exception as exc:
        raise HTTPException(503, f"TTS no disponible (perfil voz apagado): {exc}")
    return Response(content=r.content, media_type="audio/mpeg")


# ---------- Informes periódicos por correo (patrón Paloma / Resend) ----------

class ReportSubscription(BaseModel):
    email: str = Field(..., description="Correo del destinatario")
    tipo: str = Field("cliente", description="cliente|gerente")
    frecuencia: str = Field("mensual", description="demo|diaria|semanal|mensual")
    phone: str | None = Field(None, description="Teléfono del lead (clientes)")


@app.post("/api/reports/subscriptions")
def create_report_subscription(req: ReportSubscription) -> dict:
    """Opt-in a informes periódicos (cliente: estado de su seguro; gerente: KPIs)."""
    from . import reports as reports_mod
    out = reports_mod.subscribe(req.email, tipo=req.tipo,
                                frecuencia=req.frecuencia, phone=req.phone)
    if "error" in out:
        raise HTTPException(400, out["error"])
    return out


@app.get("/api/reports/subscriptions")
def get_report_subscriptions() -> list[dict]:
    from . import reports as reports_mod
    return reports_mod.list_subscriptions()


@app.delete("/api/reports/subscriptions/{sub_id}", status_code=204)
def delete_report_subscription(sub_id: int) -> None:
    from . import reports as reports_mod
    if not reports_mod.unsubscribe(sub_id):
        raise HTTPException(404, "suscripción no encontrada")


@app.post("/api/reports/subscriptions/{sub_id}/send-now")
async def send_report_now(sub_id: int) -> dict:
    """Dispara el informe de inmediato (útil para la demo)."""
    from . import reports as reports_mod
    sub = next((s for s in reports_mod.list_subscriptions() if s["id"] == sub_id), None)
    if not sub:
        raise HTTPException(404, "suscripción no encontrada")
    return await reports_mod.send_subscription_now(sub)


# ---------- Historial de conversaciones (patrón Paloma) ----------

def _parse_history_row(raw: str) -> dict | None:
    """Devuelve {role, content} si la fila es un mensaje visible del chat."""
    try:
        m = json.loads(raw)
    except (TypeError, ValueError):
        return None
    role = m.get("role")
    content = (m.get("content") or "").strip()
    if role not in ("user", "assistant") or not content or m.get("tool_calls"):
        return None
    if content.startswith("[sistema]"):  # correcciones internas del loop
        return None
    return {"role": role, "content": content}


@app.get("/api/assistant/sessions")
def assistant_sessions(limit: int = 30) -> list[dict[str, Any]]:
    """Lista las conversaciones guardadas (más recientes primero) con un
    preview del primer mensaje del usuario — para el panel de historial."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT session_id, COUNT(*) AS total, MAX(seq) AS last_seq
               FROM chat_history GROUP BY session_id
               ORDER BY MAX(seq) DESC LIMIT %s""",
            (min(int(limit), 100),)).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            first_rows = conn.execute(
                "SELECT message FROM chat_history WHERE session_id=%s ORDER BY seq ASC LIMIT 12",
                (r["session_id"],)).fetchall()
            preview, visibles = "", 0
            for fr in first_rows:
                msg = _parse_history_row(fr["message"])
                if not msg:
                    continue
                visibles += 1
                if not preview and msg["role"] == "user":
                    preview = msg["content"][:90]
            out.append({"session_id": r["session_id"], "mensajes": r["total"],
                        "preview": preview or "(conversación sin mensajes de usuario)"})
        return out
    finally:
        conn.close()


@app.get("/api/assistant/history/{session_id}")
def assistant_history(session_id: str, limit: int = 300) -> list[dict[str, str]]:
    """Mensajes visibles (usuario/asistente) de una conversación, en orden."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT message FROM chat_history WHERE session_id=%s ORDER BY seq ASC LIMIT %s",
            (session_id, min(int(limit), 1000))).fetchall()
        out = []
        for r in rows:
            msg = _parse_history_row(r["message"])
            if msg:
                out.append(msg)
        return out
    finally:
        conn.close()


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
    tipo: str | None = Field(None, description="vida|salud|auto|hogar|viaje|pyme|accidentes|exequial|mascotas|movilidad")
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
    row = conn.execute("SELECT id, stage FROM leads WHERE phone=%s", (phone,)).fetchone()
    if row:
        conn.execute(
            """UPDATE leads SET name=COALESCE(%s,name), country=%s, age=COALESCE(%s,age),
               stage=%s, updated_at=now() WHERE id=%s""",
            (name, country, age, stage, row["id"]))
        return row["id"]
    return conn.execute(
        "INSERT INTO leads (phone, name, country, age, stage) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (phone, name, country, age, stage)).fetchone()["id"]


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
        qid = conn.execute(
            """INSERT INTO quotes (lead_id, product_id, country, currency, sum_assured_usd,
               premium_monthly_usd, premium_monthly_local, breakdown)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (lead_id, o["product_id"], country, o["moneda"], o["suma_asegurada_usd"],
             o["prima_mensual_usd"], o["prima_mensual_local"],
             json.dumps(o["breakdown"], ensure_ascii=False))).fetchone()["id"]
        o["quote_id"] = qid
        quote_ids.append(qid)
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
           FROM quotes q JOIN products p ON p.id=q.product_id WHERE q.id=%s""",
        (quote_id,)).fetchone()
    if not q:
        conn.close()
        raise HTTPException(404, "Cotización no encontrada")
    lead = None
    if q["lead_id"]:
        lead = dict(conn.execute("SELECT * FROM leads WHERE id=%s", (q["lead_id"],)).fetchone() or {})
        conn.execute("UPDATE leads SET stage='documento', updated_at=now() "
                     "WHERE id=%s AND stage NOT IN ('cerrado','perdido')", (q["lead_id"],))
    conn.execute("UPDATE quotes SET status='documento' WHERE id=%s", (quote_id,))
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
    """Sugerencias de seguimiento (funnel + renovaciones/cross-sell) + alertas."""
    from .proactive import all_nudges, manager_alerts
    conn = get_conn()
    data = {"nudges_clientes": all_nudges(conn), "alertas_gerente": manager_alerts(conn)}
    conn.close()
    return data


@app.get("/api/proactive/{phone}", dependencies=[Depends(require_service)])
def proactive_for_phone(phone: str) -> dict:
    """Sugerencias de seguimiento para un cliente puntual (lo usa la skill cron)."""
    from .proactive import all_nudges
    conn = get_conn()
    data = {"nudges": all_nudges(conn, phone)}
    conn.close()
    return data


@app.get("/api/insights/leads", dependencies=[Depends(require_manager)])
def insights_leads() -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT l.*, COUNT(q.id) cotizaciones,
                  ROUND(COALESCE(SUM(q.premium_monthly_usd),0)::numeric,2)::double precision prima_usd
           FROM leads l LEFT JOIN quotes q ON q.lead_id=l.id
           GROUP BY l.id ORDER BY l.updated_at DESC LIMIT 100""").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# El servicio IA solo expone /api/*; la SPA la sirve apps/frontend (nginx enruta /).
