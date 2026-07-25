"""SegurIA API — catálogo, cotizador, leads, documentos e insights.

Consumida por las skills del agente Hermes (vía HTTP) y por la SPA (chat + panel gerencial).
"""
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Header,
                     HTTPException, Request, Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from . import backend_client, insights as insights_mod
from . import memory
from .assistant import router as assistant_router
from .campaign_broadcast import router as campaign_broadcast_router
from .embedded import router as embedded_router
from .marketing_studio import router as marketing_router
from .auth import resolve_identity
from .config import (CORS_ORIGINS, DEMO_TENANT_ID, MANAGER_API_KEY,
                     MANAGER_PHONES, SERVICE_API_KEY, WA_GATEWAY_WEBHOOK_SECRET)
from .db import COUNTRY_NAMES, get_conn, init_db, log_conversation

# Canal legado (Hermes/ConversationLog, minúsculas) -> Channel de Prisma.
# "voz" es una nota de voz DENTRO de WhatsApp (Kokoro/Voicebox local), no el
# canal de telefonía de ElevenLabs (VOICE_CALL) — para el CRM sigue siendo WhatsApp.
_LEGACY_CHANNEL_MAP = {"whatsapp": "WHATSAPP", "web": "WEB_CHAT", "voz": "WHATSAPP"}
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
app.include_router(marketing_router)  # /api/marketing/* (banners de campaña con Gemini)
app.include_router(campaign_broadcast_router)  # /api/marketing/campaigns/broadcast (envío masivo)


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador estable de la conversación")
    message: str
    phone: str | None = Field(None, description="WhatsApp del cliente si se conoce")
    manager_key: str | None = Field(None, description="API key para actuar con rol gerente")


@app.post("/api/chat")
def chat(req: ChatRequest, background_tasks: BackgroundTasks,
         authorization: str = Header(default=""),
         x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> dict:
    """Turno conversacional del agente (function calling multi-ronda con DeepSeek).

    El tenant y el rol salen del JWT del login (`Authorization: Bearer <access>`):
    `tenant_id = claims.teamId`, `role` según `claims.role`. Si no hay token válido
    cae al header `X-Tenant-Id`/tenant demo y a `manager_key`. El estado se
    particiona por `(tenant_id, user_id)`."""
    from .agent_core import run_agent
    tenant_id, role = resolve_identity(authorization, x_tenant_id, req.manager_key)
    phone = req.phone or f"web:{req.session_id}"
    log_conversation(phone, role, req.message, channel="web")
    background_tasks.add_task(backend_client.log_turn, tenant_id, phone,
                              "WEB_CHAT", role, req.message)
    result = run_agent(req.session_id, req.message, phone=req.phone or "", role=role,
                       tenant_id=tenant_id)
    if result.get("reply"):
        log_conversation(phone, "asistente", result["reply"], channel="web")
        background_tasks.add_task(backend_client.log_turn, tenant_id, phone,
                                  "WEB_CHAT", "asistente", result["reply"])
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


def require_wa_gateway(x_webhook_secret: str = Header(default="")) -> None:
    """El gateway Baileys de WhatsApp (proceso externo, reusado de Diache con
    Tequendama como tenant nuevo) — secreto propio, distinto de SERVICE_API_KEY
    (mismo criterio que ELEVENLABS_WEBHOOK_SECRET: cada tercero externo, su
    propio secreto)."""
    if not WA_GATEWAY_WEBHOOK_SECRET or x_webhook_secret != WA_GATEWAY_WEBHOOK_SECRET:
        raise HTTPException(403, "Se requiere el secreto del gateway (header X-Webhook-Secret)")


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


class WaGatewayMessage(BaseModel):
    """Shape exacto que ya manda apps/services (Diache) wa-gateway/server.js:
    {"messages":[{"from","text","id"}]} — no inventado, verificado contra el código."""
    from_: str = Field(..., alias="from")
    text: str = ""
    id: str | None = None


class WaGatewayInbound(BaseModel):
    messages: list[WaGatewayMessage] = Field(default_factory=list)


class OutboundCallRequest(BaseModel):
    phone: str = Field(..., description="Número E.164 al que se llama, ej. +573001234567")
    tenant_id: str | None = Field(None, description="Si falta, se usa el tenant demo")
    first_message: str | None = Field(None, description="Saludo inicial custom del agente")
    dynamic_variables: dict[str, Any] = Field(default_factory=dict,
                                              description="Contexto extra para el agente (nombre, motivo...)")


class CallProfilingRequest(BaseModel):
    phone: str = Field(..., description="Teléfono del cliente (mismo que dynamic_variables.phone)")
    tenant_id: str | None = Field(None, description="Si falta, se usa el tenant demo")
    transcript: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Transcript de ElevenLabs: [{role, message, time_in_call_secs}]")


class DocketIngestRequest(BaseModel):
    """Shape mínimo para alimentar el motor de versionado/QA de prompts
    (docket, ver app/docket_engine/) con una llamada real ya terminada."""
    conversation_id: str | None = Field(None, description="conversation_id de ElevenLabs, si existe")
    transcript: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Igual shape que CallProfilingRequest.transcript: [{role, message}]")


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


# Puente hacia el Lead canónico de Prisma (motor de leads del backend). El
# stage local (nuevo|descubrimiento|cotizado|documento|cerrado|perdido) no
# tiene equivalente exacto en LeadStatus — es el mapeo más cercano.
_STAGE_TO_LEAD_STATUS = {
    "nuevo": "NUEVO", "descubrimiento": "CONTACTADO", "cotizado": "COTIZADO",
    "documento": "NEGOCIACION", "cerrado": "CERRADO_GANADO", "perdido": "CERRADO_PERDIDO",
}
# El catálogo LATAM de Python tiene más tipos (hogar, viaje, pyme...) que el
# InsuranceType de Prisma (solo VIDA/AUTO/SALUD) — se omite si no mapea 1:1.
_INSURANCE_TYPE_TO_PRISMA = {"vida": "VIDA", "auto": "AUTO", "salud": "SALUD"}


def _sync_lead_to_backend(local_lead_id: int, tenant_id: str, phone: str,
                          stage: str, tipo: str | None = None) -> None:
    """Corre en background (BackgroundTasks, best-effort): empuja el estado
    del lead local hacia el Lead canónico de Prisma (POST /leads/upsert) y
    guarda el id devuelto en la fila local (prisma_lead_id) para trazabilidad."""
    prisma_id = backend_client.upsert_lead(
        tenant_id, phone,
        insurance_type=_INSURANCE_TYPE_TO_PRISMA.get((tipo or "").lower()),
        status=_STAGE_TO_LEAD_STATUS.get(stage),
    )
    if not prisma_id:
        return
    conn = get_conn()
    try:
        conn.execute("UPDATE leads SET prisma_lead_id=%s WHERE id=%s",
                     (prisma_id, local_lead_id))
        conn.commit()
    finally:
        conn.close()


@app.post("/api/quotes")
def create_quotes(req: QuoteRequest, background_tasks: BackgroundTasks) -> dict:
    """Cotiza y devuelve hasta 3 opciones a la medida; registra lead y cotizaciones."""
    conn = get_conn()
    country = req.country.upper()
    if country not in COUNTRY_NAMES:
        conn.close()
        raise HTTPException(400, f"País no soportado: {country}. Usa uno de {list(COUNTRY_NAMES)}")
    options = recommend(conn, country=country, tipo=req.tipo, age=req.age,
                        sum_assured_usd=req.sum_assured_usd,
                        budget_monthly_usd=req.budget_monthly_usd, extras=req.extras)
    stage = "cotizado" if options else "descubrimiento"
    lead_id = _upsert_lead(conn, req.phone, req.name, country, req.age, stage=stage)
    if req.phone and lead_id:
        background_tasks.add_task(_sync_lead_to_backend, lead_id, DEMO_TENANT_ID,
                                  req.phone, stage, req.tipo)
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


def _clickwrap_html(token: str, sig: dict) -> str:
    """Página pública (sin auth: el magic-link ES la credencial) que muestra
    los términos exactos y captura el clic. Ver apps/ai/app/esign.py."""
    import html as _html
    title = "Autorización de tu póliza — Tequendama Seguros"
    body = _html.escape(sig["terms_text"])
    status = sig["status"]
    done = status in ("signed", "declined", "expired")
    if status == "signed":
        estado_msg = "✅ Ya autorizaste la emisión. Puedes cerrar esta ventana."
    elif status == "declined":
        estado_msg = "Registramos que NO autorizas por ahora. Escríbenos si cambias de opinión."
    elif status == "expired":
        estado_msg = "Este link venció. Pídele a tu asesora IA que te envíe uno nuevo."
    else:
        estado_msg = ""
    tok = _html.escape(token)
    buttons = "" if done else f"""
      <button id="agree" style="background:#0a7a2f;color:#fff;border:0;border-radius:8px;
              padding:12px 20px;font-size:16px;margin-right:10px;cursor:pointer">Acepto</button>
      <button id="decline" style="background:#f1f1f1;color:#333;border:0;border-radius:8px;
              padding:12px 20px;font-size:16px;cursor:pointer">No acepto</button>"""
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:40px auto;
             padding:0 16px;color:#141e17">
<h2 style="color:#083911">{title}</h2>
<p style="background:#f1fdf0;border:1px solid #c1c9bd;border-radius:12px;padding:16px">{body}</p>
<p id="estado" style="font-weight:bold">{estado_msg}</p>
<div id="botones">{buttons}</div>
<script>
async function act(path) {{
  const a = document.getElementById('agree'), d = document.getElementById('decline');
  if (a) a.disabled = true; if (d) d.disabled = true;
  const r = await fetch(`/sign/{tok}/${{path}}`, {{ method: 'POST' }});
  if (r.ok) location.reload();
  else {{ if (a) a.disabled = false; if (d) d.disabled = false; }}
}}
const a = document.getElementById('agree'), d = document.getElementById('decline');
if (a) a.addEventListener('click', () => act('accept'));
if (d) d.addEventListener('click', () => act('decline'));
</script>
</body></html>"""


@app.get("/sign/{token}", response_class=HTMLResponse)
def sign_page(token: str) -> str:
    """Página clickwrap que abre el magic link de `generar_firma_poliza`."""
    from . import esign
    conn = get_conn()
    row = esign.get_by_token(conn, token)
    conn.close()
    if row is None:
        raise HTTPException(404, "Link de firma inválido o desconocido")
    return _clickwrap_html(token, row)


@app.post("/sign/{token}/accept")
def sign_accept(token: str, request: Request) -> dict:
    from . import esign
    conn = get_conn()
    row = esign.sign(conn, token, agree=True,
                     ip=request.client.host if request.client else None,
                     user_agent=request.headers.get("user-agent"))
    conn.close()
    if row is None:
        raise HTTPException(404, "Link de firma inválido o desconocido")
    return esign.public_view(row)


@app.post("/sign/{token}/decline")
def sign_decline(token: str, request: Request) -> dict:
    from . import esign
    conn = get_conn()
    row = esign.sign(conn, token, agree=False,
                     ip=request.client.host if request.client else None,
                     user_agent=request.headers.get("user-agent"))
    conn.close()
    if row is None:
        raise HTTPException(404, "Link de firma inválido o desconocido")
    return esign.public_view(row)


@app.post("/api/leads", dependencies=[Depends(require_service)])
def update_lead(req: LeadUpdate, background_tasks: BackgroundTasks) -> dict:
    conn = get_conn()
    stage = req.stage or "descubrimiento"
    lead_id = _upsert_lead(conn, req.phone, req.name, (req.country or "CO").upper(),
                           req.age, stage)
    conn.commit()
    conn.close()
    if lead_id:
        background_tasks.add_task(_sync_lead_to_backend, lead_id, DEMO_TENANT_ID,
                                  req.phone, stage)
    return {"lead_id": lead_id, "ok": True}


@app.post("/api/conversations", dependencies=[Depends(require_service)])
def log_message(req: ConversationLog, background_tasks: BackgroundTasks) -> dict:
    log_conversation(req.phone, req.role, req.message, req.channel)
    # Hermes (WhatsApp) no maneja tenant todavía -> tenant demo. Cuando el
    # canal web-chat propio (Next.js) llegue, deberá enviar su propio tenant.
    channel = _LEGACY_CHANNEL_MAP.get(req.channel, "WHATSAPP")
    background_tasks.add_task(backend_client.log_turn, DEMO_TENANT_ID, req.phone,
                              channel, req.role, req.message)
    return {"ok": True}


@app.get("/api/roles/{phone}", dependencies=[Depends(require_service)])
def role_for_phone(phone: str) -> dict:
    """La skill de Hermes consulta aquí si el número es de un gerente."""
    normalized = phone.replace(" ", "")
    return {"phone": normalized,
            "role": "gerente" if normalized in MANAGER_PHONES else "cliente"}


# Notas de voz educativas: cuando el turno pidió/registró un dato sensible,
# además del texto se manda un audio corto explicando POR QUÉ se pide (nunca
# cifras/coberturas — esas siempre van en texto, ver skills/voz/SKILL.md).
# Reglas deterministas (no lo redacta el LLM) para que el motivo sea siempre
# el correcto y no dependa de que el modelo lo mencione en su respuesta.
_EDUCACION_VOZ = {
    "capturar_datos_cliente": ("Te pedimos tu nombre completo y tu número de "
        "documento porque son obligatorios para poder emitir tu póliza a tu "
        "nombre. Sin estos dos datos no podemos activar tu seguro."),
    "registrar_consentimiento": ("Te pedimos autorizar el tratamiento de tus "
        "datos personales porque la ley 1581 de 2012, de habeas data, exige "
        "tu consentimiento explícito antes de poder procesar tu información "
        "para emitir la póliza."),
    "generar_firma_poliza": ("Te acabamos de enviar un link para autorizar tu "
        "póliza con un solo clic. Es tu firma electrónica: tiene la misma "
        "validez legal que una firma escrita a mano."),
}


@app.post("/channels/whatsapp/inbound/tequendama",
         dependencies=[Depends(require_wa_gateway)])
def whatsapp_inbound(req: WaGatewayInbound,
                     background_tasks: BackgroundTasks) -> dict:
    """Receptor del canal WhatsApp — alimentado por el gateway Baileys
    multi-tenant reusado (ver plan de esta sesión: NO es un gateway propio,
    es el mismo proceso de Diache con "tequendama" como tenant nuevo). Mismo
    orquestador (`run_agent`) que ya usa el chat web; se registra con
    channel=WHATSAPP real (no el WEB_CHAT hardcodeado de /api/chat)."""
    from .agent_core import run_agent

    accepted = 0
    for m in req.messages:
        phone = m.from_ if m.from_.startswith("+") else f"+{m.from_}"
        text = (m.text or "").strip()
        if not text:
            continue
        accepted += 1
        role = "gerente" if phone.replace(" ", "") in MANAGER_PHONES else "cliente"

        log_conversation(phone, role, text, channel="whatsapp")
        background_tasks.add_task(backend_client.log_turn, DEMO_TENANT_ID, phone,
                                  "WHATSAPP", role, text)

        result = run_agent(phone, text, phone=phone, role=role,
                           tenant_id=DEMO_TENANT_ID)
        reply = result.get("reply")
        if reply:
            log_conversation(phone, "asistente", reply, channel="whatsapp")
            background_tasks.add_task(backend_client.log_turn, DEMO_TENANT_ID, phone,
                                      "WHATSAPP", "asistente", reply)
            from . import whatsapp_gateway
            background_tasks.add_task(whatsapp_gateway.enviar_whatsapp, phone, reply)

            tools_del_turno = {a.get("tool") for a in (result.get("actions") or [])}
            explicacion = next((v for k, v in _EDUCACION_VOZ.items() if k in tools_del_turno), None)
            if explicacion:
                background_tasks.add_task(whatsapp_gateway.enviar_nota_voz, phone, explicacion)

    return {"received": True, "accepted": accepted}


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


# ---------- Llamadas telefónicas (motor ElevenLabs) ----------

@app.post("/api/calls/outbound", dependencies=[Depends(require_service)])
def outbound_call(req: OutboundCallRequest,
                  x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> dict:
    """Dispara una llamada saliente real con el agente de voz (ElevenLabs).

    La usan un gerente (botón "llamar" en el CRM) o la skill de seguimiento
    proactivo (cron) — nunca el chat del cliente de forma autónoma. Sin
    credenciales de ElevenLabs configuradas corre en modo demo (no llama a
    nadie, no falla). El resultado real de la llamada (transcript, duración,
    estado) lo registra el webhook post-call del backend, no este endpoint."""
    from . import calls
    tenant_id = req.tenant_id or x_tenant_id or DEMO_TENANT_ID
    return calls.iniciar_llamada(req.phone, tenant_id, first_message=req.first_message,
                                 dynamic_variables=req.dynamic_variables)


@app.post("/api/profiling/from-call", dependencies=[Depends(require_service)])
def profiling_from_call(req: CallProfilingRequest,
                        x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> dict:
    """Extrae el perfil del cliente (profiling.build_profile) a partir del
    transcript de una llamada de ElevenLabs. La llama el backend justo
    después de procesar el webhook post-call — no el chat del cliente."""
    from . import call_profiling
    tenant_id = req.tenant_id or x_tenant_id or DEMO_TENANT_ID
    return call_profiling.profile_from_call(tenant_id, req.phone, req.transcript)


@app.post("/api/docket/ingest", dependencies=[Depends(require_service)])
def docket_ingest(req: DocketIngestRequest) -> dict:
    """Registra el transcript de una llamada de ElevenLabs ya terminada en el
    motor de versionado/QA de prompts (`docket.calls`, campaña
    `tequendama-cliente`) — la llama el backend justo después de procesar el
    webhook post-call. Sin DOCKET_ENGINE_ENABLED, no hace nada (demo)."""
    from .config import DOCKET_ENGINE_ENABLED
    if not DOCKET_ENGINE_ENABLED or not req.transcript:
        return {"ok": True, "demo": True}
    from .docket_engine import store as docket_store
    turns = [{"role": "customer" if (t.get("role") or "").lower() != "agent" else "agent",
             "text": t.get("message") or ""} for t in req.transcript]
    transcript_text = "\n".join(f"{t['role']}: {t['text']}" for t in turns if t["text"])
    external_id = req.conversation_id or str(uuid.uuid4())
    c = docket_store.conn()
    try:
        call_id = docket_store.insert_call(c, "tequendama-cliente", external_id, transcript_text, turns)
        c.commit()
    finally:
        c.close()
    return {"ok": True, "demo": False, "call_id": call_id}


@app.post("/api/docket/recompute", dependencies=[Depends(require_service)])
def docket_recompute() -> dict:
    """Corre cluster → judge → optimize una vez para ambas campañas
    (tequendama-cliente/tequendama-gerente). Se dispara a mano cuando quieras
    iterar el prompt — no corre en cron. Sin DOCKET_ENGINE_ENABLED, no hace
    nada (demo)."""
    from .config import DOCKET_ENGINE_ENABLED
    if not DOCKET_ENGINE_ENABLED:
        return {"ok": True, "demo": True}
    from .docket_engine import cluster as docket_cluster
    from .docket_engine import judge as docket_judge
    from .docket_engine import optimize as docket_optimize
    from .docket_engine import seed as docket_seed
    seeded = docket_seed.run_all()
    clusters = docket_cluster.run_all()
    scores = docket_judge.run_all()
    versions = docket_optimize.run_all(list(docket_seed.CAMPAIGNS))
    return {"ok": True, "demo": False, "seeded": seeded, "clusters": clusters,
            "scores": scores, "versions": versions}


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
