"""Tequendama API — catálogo, cotizador, leads, documentos e insights.

Consumida por las skills del agente Hermes (vía HTTP) y por la SPA (chat + panel gerencial).
"""
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (BackgroundTasks, Depends, FastAPI, File, Header,
                     HTTPException, Response, UploadFile)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import backend_client, insights as insights_mod
from . import memory
from .assistant import router as assistant_router
from .embedded import router as embedded_router
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
    # Informes periódicos por correo (patrón Paloma): loop en segundo plano.
    from . import reports as reports_mod
    import asyncio as _asyncio
    reports_task = _asyncio.create_task(reports_mod.scheduler_loop())
    try:
        yield
    finally:
        reports_task.cancel()
        await memory.close_pool()


app = FastAPI(title="Tequendama Insurance API", version="0.1.0", lifespan=lifespan,
              description="Backend del asistente de venta de seguros LATAM")
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS or [],
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(assistant_router)  # POST /api/assistant/chat/stream (SSE)
app.include_router(embedded_router)   # /api/embedded/* (quote & bind para aliados)


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
                           phone: str = "", tipo: str = "") -> dict:
    """El cliente sube un documento (cédula, tarjeta de propiedad, selfie, RUT...); se
    guarda y queda disponible para que el agente lo lea con `analizar_documento`.

    Si se pasa `tipo` (cedula_frente|cedula_reverso|selfie|autorizacion_firmada|
    tarjeta_propiedad...) y un `phone` real, además queda REGISTRADO en el expediente
    KYC de esa sesión — así el canal WhatsApp (Hermes) sube la foto y la fija de una vez."""
    try:
        from . import files as files_mod
    except Exception as exc:
        raise HTTPException(503, f"Lectura de archivos no disponible: {exc}")
    content = await file.read()
    saved = files_mod.save_upload(file.filename or "documento", content)
    # lectura inmediata (best-effort) para dar feedback al cliente
    parsed = files_mod.parse_document(saved["path"], file.filename or "")
    registrado = None
    if tipo and phone and not phone.startswith("web:"):
        try:
            from . import kyc
            conn = get_conn()
            try:
                kyc.register_document(conn, _kyc_key(phone), tipo=tipo,
                                      file_id=saved["file_id"], path=saved["path"],
                                      filename=saved.get("filename"), mime=saved.get("mime"),
                                      extracted=parsed.get("campos_extraidos") or {},
                                      phone=_norm_phone(phone))
                registrado = tipo
            finally:
                conn.close()
        except Exception:
            registrado = None  # el registro KYC es best-effort; la subida no falla por él
    return {"file_id": saved["file_id"], "filename": saved.get("filename"),
            "tipo_detectado": parsed.get("tipo_detectado"),
            "campos_extraidos": parsed.get("campos_extraidos", {}),
            "resumen": parsed.get("resumen"),
            "documento_kyc_registrado": registrado}


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


# ---------- KYC / Identidad / Cierre (canal WhatsApp/Hermes vía HTTP) ----------
# Estas rutas exponen por HTTP el mismo cierre KYC que el cerebro web (run_agent)
# hace con tools, para que la skill `cierre-kyc` de Hermes lo maneje con curl. La
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


class KycDocRegister(BaseModel):
    phone: str
    tipo: str = Field(..., description="cedula_frente|cedula_reverso|selfie|autorizacion_firmada|tarjeta_propiedad|comprobante_pago|otro")
    file_id: str = Field(..., description="file_id devuelto por POST /api/assistant/upload")


@app.post("/api/kyc/documento", dependencies=[Depends(require_service)])
def kyc_registrar_documento(req: KycDocRegister) -> dict:
    """Registra en el expediente KYC un archivo ya subido (por file_id)."""
    from . import kyc
    try:
        from . import files as files_mod
        path = files_mod.path_for(req.file_id)
    except Exception:
        path = req.file_id
    conn = get_conn()
    try:
        skey = _kyc_key(req.phone)
        kyc.register_document(conn, skey, tipo=req.tipo, file_id=req.file_id,
                              path=path, phone=req.phone)
        return kyc.status(conn, skey, None)
    finally:
        conn.close()


class IdentidadVerificar(BaseModel):
    phone: str
    doc_file_id: str | None = None
    selfie_file_id: str | None = None


@app.post("/api/identidad/verificar", dependencies=[Depends(require_service)])
def identidad_verificar(req: IdentidadVerificar) -> dict:
    """Verificación biométrica cédula↔selfie de la sesión (YuNet + SFace). Devuelve
    el veredicto (aprobado|rechazado|revision|no_disponible) y lo persiste."""
    from . import kyc
    conn = get_conn()
    try:
        return kyc.run_verification(conn, _kyc_key(req.phone), phone=req.phone,
                                    doc_file_id=req.doc_file_id,
                                    selfie_file_id=req.selfie_file_id)
    finally:
        conn.close()


@app.get("/api/kyc/estado/{phone}", dependencies=[Depends(require_service)])
def kyc_estado(phone: str, insurance_type: str = "") -> dict:
    """Checklist del cierre: qué datos/documentos faltan, identidad y consentimiento."""
    from . import kyc
    conn = get_conn()
    try:
        return kyc.status(conn, _kyc_key(phone), insurance_type or None)
    finally:
        conn.close()


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
