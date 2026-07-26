"""Tequendama API — catálogo, cotizador, leads, documentos e insights.

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
from .checklist import router as checklist_router
from .landing_callback import router as landing_callback_router
from .embedded import router as embedded_router
from .marketing_studio import router as marketing_router
from .voice_live import router as voice_live_router
# from .marketing_studio import router as marketing_router
from .auth import is_staff_token, resolve_identity
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
    # Guardrail de correo (la causa nº1 de "los correos no llegan" en Railway):
    # con RESEND_API_KEY pero SIN RESEND_FROM_EMAIL se usa el remitente de
    # prueba onboarding@resend.dev, que SOLO entrega al dueño de la cuenta —
    # a los clientes nunca les llega y nada falla en apariencia.
    import os as _os
    if _os.getenv("RESEND_API_KEY") and not _os.getenv("RESEND_FROM_EMAIL"):
        import logging as _logging
        _logging.getLogger("seguria.email").error(
            "RESEND_API_KEY configurada SIN RESEND_FROM_EMAIL: los correos a "
            "clientes NO llegarán (remitente de prueba de Resend). Configura "
            "RESEND_FROM_EMAIL con un dominio verificado en resend.com/domains.")
    # Informes periódicos por correo (patrón Paloma): loop en segundo plano.
    from . import reports as reports_mod
    import asyncio as _asyncio
    reports_task = _asyncio.create_task(reports_mod.scheduler_loop())
    try:
        yield
    finally:
        reports_task.cancel()
        await memory.close_pool()


app = FastAPI(title="Tequendama API", version="0.1.0", lifespan=lifespan,
              description="Backend del asistente de venta de seguros LATAM")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS or [],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(assistant_router)  # POST /api/assistant/chat/stream (SSE)
app.include_router(embedded_router)   # /api/embedded/* (quote & bind para aliados)
app.include_router(marketing_router)  # POST /api/marketing/banner (Gemini, requiere gerente)
app.include_router(campaign_broadcast_router)  # POST /api/marketing/campaigns/broadcast (servicio-a-servicio)
app.include_router(voice_live_router)  # WS /ws/voice/live (llamada en vivo, Deepgram STT/TTS)
app.include_router(checklist_router)  # /api/checklist/{token} (público, checklist de activación)
app.include_router(landing_callback_router)  # POST /api/callback/solicitar ("déjanos tu número")


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador estable de la conversación")
    message: str
    phone: str | None = Field(None, description="WhatsApp del cliente si se conoce")
    device_id: str | None = Field(
        None, description="Identidad durable del navegador del cliente anónimo "
                          "(ancla memoria y leads entre visitas)")
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
    # Identidad: teléfono real > device_id (durable entre visitas) > session_id.
    phone = req.phone or f"web:{req.device_id or req.session_id}"
    log_conversation(phone, role, req.message, channel="web")
    background_tasks.add_task(backend_client.log_turn, tenant_id, phone,
                              "WEB_CHAT", role, req.message)
    result = run_agent(req.session_id, req.message, phone=phone, role=role,
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
async def assistant_upload(file: UploadFile = File(...), session_id: str = "",
                           phone: str = "") -> dict:
    """El cliente sube un documento (tarjeta de propiedad, RUT, examen...); se guarda
    y queda disponible para que el agente lo lea con `analizar_documento`.

    Nota: la verificación de identidad (cédula + selfie + prueba de vida) NO pasa por
    aquí — va por el link de Didit (`generar_verificacion_identidad`, ver app/kyc.py)."""
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
def assistant_sessions(limit: int = 30,
                       authorization: str = Header(default="")) -> list[dict[str, Any]]:
    """Lista las conversaciones guardadas (más recientes primero) con un
    preview del primer mensaje del usuario — para el panel de historial.

    Solo staff (Bearer de gerente/admin/vendedor): el listado expone las
    conversaciones de TODOS los clientes. El cliente anónimo restaura la suya
    por `/api/assistant/history/{tenant}:{session_id}`, cuya clave solo él
    conoce (UUID no adivinable en su localStorage)."""
    if not is_staff_token(authorization):
        raise HTTPException(403, "Solo el personal autorizado puede listar el historial")
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
    """Shape que manda apps/services/baileys-bridge/index.js::forwardToTequendama.
    `text` viene vacío cuando el mensaje es una nota de voz — en ese caso trae
    `audio_base64`/`audio_mimetype` en su lugar (ver whatsapp_inbound, que la
    transcribe con Deepgram antes de pasarla al agente)."""
    from_: str = Field(..., alias="from")
    text: str = ""
    id: str | None = None
    audio_base64: str | None = None
    audio_mimetype: str | None = None


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


# ---------- Panel "Agente IA": precios y conocimiento (gerencia) ----------

def require_manager_flex(authorization: str = Header(default=""),
                         x_api_key: str = Header(default=""),
                         x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> str:
    """Gerencia autenticada por cualquiera de las dos vías: el JWT del login
    (claims.role GERENTE/ADMIN, la vía normal de la SPA) o la API key
    histórica `X-Api-Key` (scripts/pruebas). Devuelve el tenant resuelto."""
    tenant_id, role = resolve_identity(authorization, x_tenant_id, x_api_key)
    if role != "gerente":
        raise HTTPException(403, "Solo gerencia puede administrar el agente")
    return tenant_id


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4000)


class KnowledgeUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    content: str | None = Field(None, min_length=1, max_length=4000)
    active: bool | None = None


class ProductUpdate(BaseModel):
    nombre: str | None = Field(None, min_length=1, max_length=160)
    tipo: str | None = Field(None, min_length=1, max_length=40)
    aseguradora: str | None = Field(None, min_length=1, max_length=120)
    prima_base_usd: float | None = Field(None, ge=0)
    suma_base_usd: float | None = Field(None, ge=0)
    coberturas: list[str] | None = None
    paises: list[str] | None = None


class ProductCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    tipo: str = Field(min_length=1, max_length=40)
    aseguradora: str = Field(min_length=1, max_length=120)
    prima_base_usd: float = Field(ge=0)
    suma_base_usd: float = Field(ge=0)
    coberturas: list[str] = Field(default_factory=list)
    paises: list[str] = Field(default_factory=lambda: ["CO"])


@app.get("/api/knowledge")
def knowledge_list(tenant_id: str = Depends(require_manager_flex)) -> list[dict]:
    from . import knowledge
    return knowledge.list_entries(tenant_id)


@app.post("/api/knowledge", status_code=201)
def knowledge_create(req: KnowledgeCreate,
                     tenant_id: str = Depends(require_manager_flex)) -> dict:
    from . import knowledge
    return knowledge.create_entry(tenant_id, req.title, req.content)


@app.post("/api/knowledge/upload", status_code=201)
async def knowledge_upload(file: UploadFile = File(...),
                           tenant_id: str = Depends(require_manager_flex)) -> dict:
    """Sube un documento (PDF/DOCX/TXT) y lo convierte en conocimiento del
    agente: extrae su texto y lo guarda como entrada activa."""
    from . import knowledge
    content = await file.read()
    if not content:
        raise HTTPException(422, "Archivo vacío")
    try:
        return knowledge.create_from_document(
            tenant_id, file.filename or "documento", content)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.patch("/api/knowledge/{entry_id}")
def knowledge_update(entry_id: int, req: KnowledgeUpdate,
                     tenant_id: str = Depends(require_manager_flex)) -> dict:
    from . import knowledge
    if req.title is None and req.content is None and req.active is None:
        raise HTTPException(422, "Nada que actualizar")
    row = knowledge.update_entry(tenant_id, entry_id, title=req.title,
                                 content=req.content, active=req.active)
    if not row:
        raise HTTPException(404, "Entrada no encontrada")
    return row


@app.delete("/api/knowledge/{entry_id}", status_code=204)
def knowledge_delete(entry_id: int,
                     tenant_id: str = Depends(require_manager_flex)) -> Response:
    from . import knowledge
    if not knowledge.delete_entry(tenant_id, entry_id):
        raise HTTPException(404, "Entrada no encontrada")
    return Response(status_code=204)


def _product_out(row: dict) -> dict:
    out = dict(row)
    out["coberturas"] = json.loads(out["coberturas"]) if out.get("coberturas") else []
    out["paises"] = json.loads(out["paises"]) if out.get("paises") else []
    return out


def _slugify(text: str) -> str:
    import re
    import unicodedata
    base = unicodedata.normalize("NFD", text.lower())
    base = "".join(c for c in base if unicodedata.category(c) != "Mn")
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:48] or "producto"


@app.post("/api/products", status_code=201)
def product_create(req: ProductCreate,
                   _tenant_id: str = Depends(require_manager_flex)) -> dict:
    """Alta de producto desde el panel gerencial. Nace `editado_manual=TRUE`
    para que el seed del catálogo JSON nunca lo pise. Disponible de inmediato
    en el cotizador del agente."""
    base_id = _slugify(req.nombre)
    conn = get_conn()
    try:
        pid, n = base_id, 1
        while conn.execute("SELECT 1 FROM products WHERE id = %s", (pid,)).fetchone():
            n += 1
            pid = f"{base_id}-{n}"
        row = conn.execute(
            """INSERT INTO products
               (id, tipo, nombre, aseguradora, paises, suma_base_usd,
                prima_base_usd, prima_por_dia, coberturas, factores, editado_manual)
               VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,'{}',TRUE)
               RETURNING id, tipo, nombre, aseguradora, paises, suma_base_usd,
                         prima_base_usd, coberturas""",
            (pid, req.tipo.strip().lower(), req.nombre.strip(), req.aseguradora.strip(),
             json.dumps([p.upper() for p in req.paises]), req.suma_base_usd,
             req.prima_base_usd, json.dumps(req.coberturas, ensure_ascii=False))).fetchone()
        conn.commit()
    finally:
        conn.close()
    return _product_out(row)


@app.patch("/api/products/{product_id}")
def product_update(product_id: str, req: ProductUpdate,
                   _tenant_id: str = Depends(require_manager_flex)) -> dict:
    """Edición de catálogo desde el panel gerencial. Marca `editado_manual`
    para que el seed del catálogo JSON no pise el cambio en el próximo boot.
    El cotizador (`quoting.recommend`) lee esta misma tabla: el nuevo precio
    rige de inmediato en las cotizaciones del agente."""
    sets, params = ["editado_manual = TRUE"], []
    if req.nombre is not None:
        sets.append("nombre = %s")
        params.append(req.nombre.strip())
    if req.tipo is not None:
        sets.append("tipo = %s")
        params.append(req.tipo.strip().lower())
    if req.aseguradora is not None:
        sets.append("aseguradora = %s")
        params.append(req.aseguradora.strip())
    if req.prima_base_usd is not None:
        sets.append("prima_base_usd = %s")
        params.append(req.prima_base_usd)
    if req.suma_base_usd is not None:
        sets.append("suma_base_usd = %s")
        params.append(req.suma_base_usd)
    if req.coberturas is not None:
        sets.append("coberturas = %s")
        params.append(json.dumps(req.coberturas, ensure_ascii=False))
    if req.paises is not None:
        sets.append("paises = %s")
        params.append(json.dumps([p.upper() for p in req.paises]))
    if len(sets) == 1:
        raise HTTPException(422, "Nada que actualizar")
    conn = get_conn()
    try:
        row = conn.execute(
            f"""UPDATE products SET {', '.join(sets)} WHERE id = %s
                RETURNING id, tipo, nombre, aseguradora, paises, suma_base_usd,
                          prima_base_usd, coberturas""",
            (*params, product_id)).fetchone()
        conn.commit()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Producto no encontrado")
    return _product_out(row)


@app.delete("/api/products/{product_id}", status_code=204)
def product_delete(product_id: str,
                   _tenant_id: str = Depends(require_manager_flex)) -> Response:
    """Baja de producto del catálogo. Bloquea si tiene cotizaciones que lo
    referencian (integridad): en ese caso el gerente debe desactivarlo, no
    borrarlo. Best-effort para productos sin dependencias."""
    conn = get_conn()
    try:
        used = conn.execute(
            "SELECT 1 FROM quotes WHERE product_id = %s LIMIT 1", (product_id,)).fetchone()
        if used:
            raise HTTPException(
                409, "El producto tiene cotizaciones asociadas; no se puede eliminar")
        cur = conn.execute("DELETE FROM products WHERE id = %s", (product_id,))
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Producto no encontrado")
    return Response(status_code=204)


@app.get("/api/insights/product-ideas")
def insights_product_ideas(tenant_id: str = Depends(require_manager_flex)) -> dict:
    """Muro de ideas: demanda de productos NO cubiertos detectada en las
    conversaciones de clientes, con viabilidad explicada."""
    from .product_ideas import product_ideas
    return product_ideas(tenant_id)


@app.get("/api/insights/combos")
def insights_combos(_tenant_id: str = Depends(require_manager_flex)) -> dict:
    """Combos de seguros más comprados: combinaciones de tipos que un mismo
    cliente tiene vigentes a la vez (cross-sell real), rankeadas por
    frecuencia. Ver insights.by_combo."""
    conn = get_conn()
    try:
        return {"combos": insights_mod.by_combo(conn)}
    finally:
        conn.close()


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
# Los 10 tipos del catálogo LATAM ya tienen equivalente 1:1 en el
# InsuranceType de Prisma (antes solo tenía VIDA/AUTO/SALUD y los otros 7 se
# sincronizaban sin tipo — ver migración 20260725120000_insurers).
_INSURANCE_TYPE_TO_PRISMA = {
    "vida": "VIDA", "auto": "AUTO", "salud": "SALUD", "hogar": "HOGAR",
    "viaje": "VIAJE", "pyme": "PYME", "accidentes": "ACCIDENTES",
    "exequial": "EXEQUIAL", "mascotas": "MASCOTAS", "movilidad": "MOVILIDAD",
}


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


# ---------- Voz (Deepgram): dos tools, transcribir/generar, ver voice_deepgram.py ----------

@app.post("/api/voice/transcribe", dependencies=[Depends(require_service)])
async def voice_transcribe(file: UploadFile | None = File(default=None),
                          audio_url: str = "") -> dict:
    """Tool STT: nota de voz -> texto. Pasa un archivo (multipart, ej. la nota
    de voz que Hermes ya descargó de WhatsApp) o `audio_url` si es accesible
    por Deepgram directo. Siempre devuelve JSON, nunca lanza excepción."""
    from . import voice_deepgram
    if file is not None:
        content = await file.read()
        return voice_deepgram.transcribir(
            audio_bytes=content,
            content_type=file.content_type or "audio/ogg")
    if audio_url:
        return voice_deepgram.transcribir(audio_url=audio_url)
    raise HTTPException(400, "Falta 'file' (multipart) o 'audio_url'")


class VoiceGenerateRequest(BaseModel):
    texto: str = Field(..., description="Texto a convertir en nota de voz")


@app.post("/api/voice/generar", dependencies=[Depends(require_service)])
def voice_generar(req: VoiceGenerateRequest) -> dict:
    """Tool TTS: texto -> nota de voz (mp3). Devuelve {"audio_url": "/api/voice/audio/..."}
    para que quien lo llama (Hermes) la descargue y la mande por WhatsApp."""
    from . import voice_deepgram
    return voice_deepgram.generar_audio(req.texto)


@app.get("/api/voice/audio/{filename}")
def voice_audio(filename: str) -> FileResponse:
    from .config import AUDIO_DIR
    path = (AUDIO_DIR / filename).resolve()
    if not path.is_file() or path.parent != AUDIO_DIR.resolve():
        raise HTTPException(404, "Audio no encontrado")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


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


def _kyc_html(token: str, row: dict) -> str:
    """Página de verificación de identidad: consentimiento biométrico (NUESTRO)
    -> redirige a la sesión hosteada de Didit (captura de cédula + selfie +
    liveness, interfaz de ellos) -> Didit vuelve a `/kyc/{token}/callback` con
    el resultado. Ver apps/ai/app/kyc.py para por qué la captura vive en Didit
    y no en una página propia (tier gratis + mejor liveness que un JS casero)."""
    import html as _html

    from . import kyc as _kyc_mod
    tok = _html.escape(token)
    status = row["status"]
    consented = bool(row.get("consent_biometrico"))
    done = status in ("aprobado", "revision_manual", "rechazado", "expirado")
    redirigiendo = status == "redirigido" and row.get("session_url")
    resultado_msg = {
        "aprobado": "✅ Identidad verificada. Puedes cerrar esta ventana y volver al chat.",
        "revision_manual": "🕐 Tu verificación quedó en revisión de un asesor. Te confirmamos en menos de 24 horas.",
        "rechazado": "No pudimos verificar tu identidad por este medio. Un asesor te contactará.",
        "expirado": "Este link venció. Pídele a tu asesora IA que te envíe uno nuevo.",
    }.get(status, "")
    consentimiento_txt = _html.escape(_kyc_mod.CONSENTIMIENTO_BIOMETRICO)
    session_url = _html.escape(row.get("session_url") or "")

    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verifica tu identidad — Tequendama Seguros</title>
<style>
body{{font-family:Arial,Helvetica,sans-serif;max-width:480px;margin:24px auto;padding:0 16px;color:#141e17}}
h2{{color:#083911}}
.card{{background:#f1fdf0;border:1px solid #c1c9bd;border-radius:12px;padding:16px;margin:12px 0}}
button,a.btn{{background:#0a7a2f;color:#fff;border:0;border-radius:8px;padding:12px 20px;font-size:16px;
       margin:6px 6px 6px 0;cursor:pointer;display:inline-block;text-decoration:none}}
button.secondary{{background:#f1f1f1;color:#333}}
#estado{{font-weight:bold}}
.oculto{{display:none}}
</style></head>
<body>
<h2>Verifica tu identidad</h2>
<div id="paso-consentimiento" class="{'oculto' if consented or done else ''}">
  <div class="card">{consentimiento_txt}</div>
  <button id="btn-acepto">Acepto</button>
  <button id="btn-no-acepto" class="secondary">No acepto</button>
</div>
<div id="paso-redirigiendo" class="{'oculto' if not redirigiendo else ''}">
  <p>Te llevamos a la verificación segura (cédula + selfie)...</p>
  <a class="btn" id="link-continuar" href="{session_url}">Continuar verificación</a>
</div>
<div id="paso-resultado" class="{'oculto' if not done else ''}">
  <p id="estado">{resultado_msg}</p>
</div>
<p id="error" style="color:#a33"></p>
<script>
const TOKEN = "{tok}";
function err(msg) {{ document.getElementById('error').textContent = msg; }}

document.getElementById('btn-acepto')?.addEventListener('click', async () => {{
  const r = await fetch(`/kyc/${{TOKEN}}/consent`, {{method: 'POST'}});
  const data = await r.json();
  if (r.ok && data.session_url) {{
    window.location.href = data.session_url;   // directo a Didit, sin paso intermedio
  }} else if (r.ok) {{
    location.reload();   // modo demo: ya quedó resuelto, muestra el resultado
  }} else {{
    err(data.error || 'No se pudo iniciar la verificación.');
  }}
}});
document.getElementById('btn-no-acepto')?.addEventListener('click', () => {{
  document.getElementById('paso-consentimiento').innerHTML =
    '<p>Sin tu autorización no podemos verificar tu identidad ni emitir la póliza. ' +
    'Escríbele a tu asesora IA si cambias de opinión.</p>';
}});
{"window.location.href = " + repr(session_url) + ";" if redirigiendo else ""}
</script>
</body></html>"""


@app.get("/kyc/{token}", response_class=HTMLResponse)
def kyc_page(token: str) -> str:
    from . import kyc
    conn = get_conn()
    row = kyc.get_by_token(conn, token)
    conn.close()
    if row is None:
        raise HTTPException(404, "Link de verificación inválido o desconocido")
    return _kyc_html(token, row)


@app.post("/kyc/{token}/consent")
def kyc_consent(token: str, request: Request) -> dict:
    """Registra el consentimiento biométrico y de una vez crea la sesión de
    Didit — el frontend redirige con la `session_url` que devuelve."""
    from . import kyc
    conn = get_conn()
    row = kyc.record_consent(conn, token, ip=request.client.host if request.client else None,
                             user_agent=request.headers.get("user-agent"))
    if row is None:
        conn.close()
        raise HTTPException(404, "Link de verificación inválido o desconocido")
    if row["status"] != "consentido":
        conn.close()
        return kyc.public_view(row)
    result = kyc.create_didit_session(conn, token)
    conn.close()
    return result


@app.get("/kyc/{token}/callback", response_class=HTMLResponse)
def kyc_callback(token: str) -> str:
    """A donde Didit redirige el navegador del cliente al terminar su sesión
    (captura de cédula/selfie). Refresca el veredicto (`GET .../decision/`,
    ver kyc.refresh_decision) y muestra el resultado."""
    from . import kyc
    conn = get_conn()
    row = kyc.get_by_token(conn, token)
    if row is None:
        conn.close()
        raise HTTPException(404, "Link de verificación inválido o desconocido")
    row = kyc.refresh_decision(conn, row)
    conn.close()
    return _kyc_html(token, row)


@app.get("/kyc/{token}/status")
def kyc_status(token: str) -> dict:
    from . import kyc
    conn = get_conn()
    row = kyc.get_by_token(conn, token)
    if row is None:
        conn.close()
        raise HTTPException(404, "Link de verificación inválido o desconocido")
    row = kyc.refresh_decision(conn, row)
    conn.close()
    return kyc.public_view(row)


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


# ---------- Datos / consentimiento / emisión (canal WhatsApp/Hermes vía HTTP) ----------
# Estas rutas exponen por HTTP los mismos pasos de cierre que el cerebro web
# (run_agent) hace con tools, para que las skills de Hermes los manejen con curl.
# La identidad va aparte, por el link de Didit (ver `/kyc/{token}` arriba). La
# sesión se particiona por `{DEMO_TENANT_ID}:{phone}` (igual que en agent_core).

def _norm_phone(phone: str) -> str:
    """Normaliza el teléfono para que la clave de sesión coincida entre llamadas.

    En un query string el `+` se decodifica como espacio (ej. subir la foto con
    `?phone=+57...`), así que unificamos: sin espacios y con un único `+` inicial.
    Las claves web (`web:...`) se dejan intactas."""
    p = (phone or "").strip()
    if not p or p.startswith("web:"):
        return p
    p = p.replace(" ", "")
    return p if p.startswith("+") else "+" + p


def _kyc_key(phone: str) -> str:
    return f"{DEMO_TENANT_ID}:{_norm_phone(phone)}"


class DatosClienteReq(BaseModel):
    phone: str
    full_name: str | None = None
    document_id: str | None = None
    document_type: str | None = "CC"
    birth_date: str | None = None
    email: str | None = None
    city: str | None = None
    campos: dict[str, Any] = Field(default_factory=dict,
                                   description="Otros campos KYC/SARLAFT/salud {id: valor}")


@app.post("/api/datos-cliente", dependencies=[Depends(require_service)])
def datos_cliente(req: DatosClienteReq) -> dict:
    """Captura/actualiza los datos del cliente para el cierre (checkout + intake)."""
    from .agent_core import (_save_checkout, _save_intake, _get_checkout,
                             _checkout_missing)
    conn = get_conn()
    try:
        skey = _kyc_key(req.phone)
        _save_checkout(conn, skey, full_name=req.full_name, document_id=req.document_id,
                       document_type=req.document_type or "CC", birth_date=req.birth_date,
                       email=req.email, city=req.city, phone=req.phone)
        if req.campos:
            _save_intake(conn, skey, req.campos)
        sess = _get_checkout(conn, skey)
        return {"ok": True, "faltan_minimos": _checkout_missing(sess)}
    finally:
        conn.close()


class ConsentimientoReq(BaseModel):
    phone: str
    acepta: bool


@app.post("/api/consentimiento", dependencies=[Depends(require_service)])
def consentimiento(req: ConsentimientoReq) -> dict:
    """Registra el consentimiento de habeas data (Ley 1581/2012)."""
    from datetime import datetime as _dt
    from .agent_core import _save_checkout
    if not req.acepta:
        raise HTTPException(400, "sin consentimiento explícito no se puede emitir")
    conn = get_conn()
    try:
        _save_checkout(conn, _kyc_key(req.phone), consent=1,
                       consent_at=_dt.utcnow().isoformat())
        return {"ok": True, "consentimiento": True}
    finally:
        conn.close()


class EmitirReq(BaseModel):
    phone: str
    insurance_type: str = "VIDA"
    monthly_premium_cop: float = 0
    coverage: dict[str, Any] = Field(default_factory=dict)
    payment_method: str = "simulado"
    payment_reference: str | None = None


@app.post("/api/emitir", dependencies=[Depends(require_service)])
def emitir(req: EmitirReq) -> dict:
    """Emite la póliza aplicando el gate KYC (documentos + identidad verificada +
    datos + consentimiento + underwriting + pago). Si faltan requisitos, los devuelve."""
    from .agent_core import _emitir_poliza
    conn = get_conn()
    try:
        args = {"insurance_type": req.insurance_type,
                "monthly_premium_cop": req.monthly_premium_cop,
                "coverage": req.coverage, "payment_method": req.payment_method,
                "payment_reference": req.payment_reference}
        return _emitir_poliza(conn, args, phone=_norm_phone(req.phone), tenant_id=DEMO_TENANT_ID)
    finally:
        conn.close()


# "Te llamamos" (POST /api/callback/solicitar) vive en app/landing_callback.py,
# registrado como router arriba — no lo dupliques acá: el router gana por orden
# de registro y este handler quedaría muerto en silencio.

@app.get("/api/callback/opciones")
def callback_opciones() -> dict:
    """Ramos que ofrece el formulario de "te llamamos" — el front los pinta como
    chips en vez de tenerlos duplicados en el bundle."""
    from .callback import INTERESES
    return {"intereses": [{"id": k, "label": v} for k, v in INTERESES.items()]}


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

        if not text and m.audio_base64:
            from . import voice_deepgram
            import base64
            audio_bytes = base64.b64decode(m.audio_base64)
            transcripcion = voice_deepgram.transcribir(
                audio_bytes=audio_bytes, content_type=m.audio_mimetype or "audio/ogg")
            text = (transcripcion.get("texto") or "").strip()
            if not text:
                # Sin DEEPGRAM_API_KEY (demo), falla o silencio real: no hay
                # texto que darle al agente — se lo decimos y seguimos con el
                # siguiente mensaje, nunca rompe el webhook.
                from . import whatsapp_gateway
                background_tasks.add_task(
                    whatsapp_gateway.enviar_whatsapp, phone,
                    "No pude escuchar bien tu nota de voz — ¿me la escribes?")
                continue

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


class ChecklistCallRequest(BaseModel):
    phone: str = Field(..., description="Número E.164 del cliente con checklist estancado")
    tenant_id: str | None = Field(None, description="Si falta, se usa el tenant demo")


@app.post("/api/calls/checklist", dependencies=[Depends(require_service)])
def checklist_reactivation_call(req: ChecklistCallRequest,
                                x_tenant_id: str = Header(default="", alias="X-Tenant-Id")) -> dict:
    """Llamada de reactivación de Camila para un checklist de activación
    estancado (ver `proactive.checklist_nudges`). La usa la skill de Hermes
    `reactivar-checklist` — no el chat del cliente. Reenvía primero el link
    vigente del checklist (rota su token) y luego dispara la llamada."""
    from . import calls
    tenant_id = req.tenant_id or x_tenant_id or DEMO_TENANT_ID
    return calls.iniciar_llamada_reactivacion_checklist(req.phone, tenant_id)


@app.post("/api/benefits/check", dependencies=[Depends(require_service)])
def benefits_check() -> dict:
    """Corre el vesting de beneficios (ver `benefits.py` — 2 entradas a parque
    en el mes 3, bono de droguería en el mes 6, noche de hotel en el mes 12
    de póliza vigente continua) y entrega lo recién desbloqueado por WhatsApp.
    La usa la skill de Hermes `beneficios-vesting` (cron diario)."""
    from . import benefits
    conn = get_conn()
    try:
        entregados = benefits.check_and_unlock(conn)
        return {"entregados": entregados, "n": len(entregados)}
    finally:
        conn.close()


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
