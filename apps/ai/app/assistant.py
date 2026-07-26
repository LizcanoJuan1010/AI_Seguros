"""Chat por STREAMING SSE — contrato de FUSION.md.

`POST /api/assistant/chat/stream` devuelve `text/event-stream`. Reusa el
orquestador de function calling de `agent_core` en modo streaming (AsyncOpenAI),
suma la memoria multi-tenant al system prompt y persiste el turno. Sin
`DEEPSEEK_API_KEY` corre un modo demo que igual streamea y cotiza de verdad.

Eventos emitidos (data = JSON en una línea):
  thinking · token · tool_start · tool_result · document · quick_replies · done · error
"""
import asyncio
import json
import logging
import re
import unicodedata
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import backend_client, config, memory
from .auth import resolve_identity
from .agent_core import (MAX_TOOL_ROUNDS, SUGERENCIAS_RE, SYSTEM_PROMPT_GERENTE,
                         SYSTEM_PROMPT_WEB, TOOLS_SCHEMA,
                         _append_history, _exec_tool, _load_history)
from .config import MANAGER_PHONES
from .db import COUNTRY_NAMES, get_conn, log_conversation

log = logging.getLogger("seguria.assistant")
router = APIRouter()


class StreamChatRequest(BaseModel):
    session_id: str = Field(..., description="Identificador estable de la conversación")
    message: str
    phone: str | None = Field(None, description="WhatsApp del cliente si se conoce")
    device_id: str | None = Field(
        None, description="Identidad durable del navegador del cliente anónimo "
                          "(la 'cuenta' sin registro: ancla memoria y leads entre visitas)")
    manager_key: str | None = Field(None, description="API key para actuar como gerente")


def _frame(event: str, data: dict) -> str:
    """Serializa un frame SSE `event: X\\ndata: {json}\\n\\n`."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class _MarkerBuffer:
    """Acumula el texto del modelo y retiene la línea `SUGERENCIAS:` (no se
    streamea al usuario). Deja salir todo menos una cola del tamaño del marcador
    para poder detectarlo antes de emitirlo."""

    def __init__(self, marker: str = "SUGERENCIAS:") -> None:
        self.marker = marker
        self.buf = ""
        self.flushed = 0
        self.stopped = False

    def push(self, delta: str) -> str:
        self.buf += delta
        if self.stopped:
            return ""
        idx = self.buf.find(self.marker)
        if idx != -1:
            out = self.buf[self.flushed:idx]
            self.flushed = idx
            self.stopped = True
            return out
        safe_end = max(self.flushed, len(self.buf) - len(self.marker))
        out = self.buf[self.flushed:safe_end]
        self.flushed = safe_end
        return out

    def finish(self) -> str:
        if self.stopped:
            return ""
        out = self.buf[self.flushed:]
        self.flushed = len(self.buf)
        return out

    @property
    def full(self) -> str:
        return self.buf


# Herramientas del cierre autónomo: su salida se mapea a eventos checkout_step/
# policy/payment_link/underwriting (no al evento `document`, que es para la cotización).
_CHECKOUT_TOOLS = {"capturar_datos_cliente", "registrar_consentimiento", "emitir_poliza",
                   "generar_link_pago", "verificar_pago", "solicitar_aclaracion",
                   "evaluar_riesgo"}

_UW_LABEL = {"AUTO_APPROVE": "Aprobación automática",
             "REFER": "Escalado a un asesor",
             "DECLINE": "No asegurable por este canal"}


def _summarize_tool(name: str, result) -> tuple[str, dict]:
    """Resumen humano + meta compacta para el evento `tool_result`."""
    if isinstance(result, dict) and result.get("error"):
        return f"Error: {result['error']}", {}
    if name == "cotizar" and isinstance(result, dict) and result.get("opciones") is not None:
        ops = result["opciones"]
        return (f"{len(ops)} opciones cotizadas",
                {"opciones": len(ops), "quote_ids": [o.get("quote_id") for o in ops]})
    if name == "generar_documento" and isinstance(result, dict) and result.get("download_url"):
        return "Documento PDF generado", {"download_url": result["download_url"]}
    if name == "buscar_productos" and isinstance(result, list):
        return f"{len(result)} productos", {"n": len(result)}
    if name == "listar_leads" and isinstance(result, list):
        return f"{len(result)} leads", {"n": len(result)}
    if name == "obtener_insights":
        return "Insights de negocio", {}
    if name == "actualizar_lead":
        return "Lead actualizado", {}
    if name == "capturar_datos_cliente" and isinstance(result, dict):
        faltan = result.get("faltan") or []
        return (("Datos capturados" if not faltan else f"Faltan datos: {', '.join(faltan)}"),
                {"faltan": faltan})
    if name == "registrar_consentimiento" and isinstance(result, dict):
        return "Consentimiento registrado", {}
    if name == "evaluar_riesgo" and isinstance(result, dict) and result.get("decision"):
        return (_UW_LABEL.get(result["decision"], result["decision"]),
                {"decision": result["decision"]})
    if name == "proponer_renovacion" and isinstance(result, dict) and result.get("poliza"):
        dias = result["poliza"].get("vence_en_dias")
        return (f"Renovación lista (vence en {dias} días)", {"vence_en_dias": dias})
    if name == "reportar_siniestro" and isinstance(result, dict) and result.get("claim_number"):
        return (f"Reclamo registrado {result['claim_number']}",
                {"claim_number": result["claim_number"], "status": result.get("status")})
    if name == "estado_siniestro" and isinstance(result, dict) and result.get("claim_number"):
        return (f"Reclamo {result.get('status', '')}",
                {"claim_number": result["claim_number"], "status": result.get("status")})
    if name == "documentos_siniestro" and isinstance(result, dict):
        return f"{len(result.get('documentos', []))} documentos requeridos", {}
    if name == "emitir_poliza" and isinstance(result, dict) and result.get("policyNumber"):
        return (f"Póliza emitida {result['policyNumber']}",
                {"policyNumber": result["policyNumber"], "degraded": result.get("degraded", False)})
    if name == "generar_link_pago" and isinstance(result, dict) and result.get("reference"):
        return (("Pago demo preparado" if result.get("demo") else "Link de pago generado"),
                {"reference": result["reference"], "checkout_url": result.get("checkout_url")})
    if name == "verificar_pago" and isinstance(result, dict) and result.get("reference"):
        return (f"Pago {result.get('estado', result.get('status', ''))}",
                {"reference": result["reference"], "status": result.get("status")})
    if name == "solicitar_aclaracion" and isinstance(result, dict) and result.get("reference"):
        return (("Pago anulado" if result.get("status") == "VOIDED" else "Aclaración registrada"),
                {"reference": result["reference"], "status": result.get("status")})
    return "Listo", {}


def _payment_frame(result: dict) -> str:
    """Frame SSE `payment_link` con el estado del pago (tarjeta en el chat)."""
    return _frame("payment_link", {
        "reference": result.get("reference"),
        "checkout_url": result.get("checkout_url"),
        "amount_cop": result.get("amount_cop"),
        "concept": result.get("concept"),
        "status": result.get("status") or "PENDING",
        "provider": result.get("provider"),
        "demo": bool(result.get("demo")),
    })


def _checkout_frames(name: str, result) -> list[str]:
    """Mapea la salida de las herramientas de cierre a eventos SSE
    `checkout_step` (datos/consentimiento/pago/emision), `payment_link` y
    `policy`."""
    frames: list[str] = []
    if not isinstance(result, dict):
        return frames
    if name in ("generar_link_pago", "verificar_pago", "solicitar_aclaracion"):
        if result.get("reference"):
            if name == "generar_link_pago":
                frames.append(_frame("checkout_step", {"step": "pago"}))
            frames.append(_payment_frame(result))
        return frames
    if name == "capturar_datos_cliente":
        frames.append(_frame("checkout_step", {"step": "datos",
                                               "fields": result.get("faltan", [])}))
    elif name == "registrar_consentimiento" and result.get("consentimiento"):
        frames.append(_frame("checkout_step", {"step": "consentimiento"}))
    elif name == "evaluar_riesgo" and result.get("decision"):
        frames.append(_frame("underwriting", {
            "decision": result["decision"],
            "label": _UW_LABEL.get(result["decision"], result["decision"]),
            "reasons": result.get("reasons", []),
            "segmento_riesgo": result.get("segmento_riesgo"),
        }))
    elif name == "emitir_poliza" and result.get("underwriting") and not result.get("policyNumber"):
        uw = result["underwriting"]
        frames.append(_frame("underwriting", {
            "decision": uw.get("decision"),
            "label": _UW_LABEL.get(uw.get("decision"), uw.get("decision")),
            "reasons": uw.get("reasons", []),
            "segmento_riesgo": uw.get("segmento_riesgo"),
        }))
    elif name == "emitir_poliza" and result.get("policyNumber"):
        frames.append(_frame("checkout_step", {"step": "pago"}))
        frames.append(_frame("checkout_step", {"step": "emision"}))
        if result.get("download_url"):
            frames.append(_frame("policy", {"policyNumber": result["policyNumber"],
                                            "download_url": result["download_url"],
                                            "title": "Póliza vigente"}))
    elif name in ("reportar_siniestro", "estado_siniestro") and result.get("claim_number"):
        # Las banderas de fraude son internas: NUNCA viajan al navegador.
        frames.append(_frame("claim", {
            "claimNumber": result["claim_number"],
            "status": (result.get("status") or "REPORTADO").upper(),
            "tipo": result.get("tipo"),
            "poliza": result.get("poliza"),
            "documentos_requeridos": result.get("documentos_requeridos", []),
            "title": ("Reclamo registrado" if name == "reportar_siniestro"
                      else "Estado de tu reclamo"),
        }))
    elif name == "generar_formulario" and result.get("formulario"):
        frames.append(_frame("form", result["formulario"]))
    elif name == "perfilar_cliente" and result.get("resumen_perfil"):
        frames.append(_frame("profile", result))
    elif name == "solicitar_informacion" and isinstance(result.get("porcentaje"), int):
        frames.append(_frame("intake_progress", {"tipo": result.get("tipo"),
                                                 "porcentaje": result["porcentaje"],
                                                 "siguientes": result.get("siguientes", [])}))
    return frames


# ---------- Runner con DeepSeek (streaming real) ----------

async def _run_llm(session_id: str, message: str, mem_ctx: str, role: str,
                   user_id: str, tenant_id: str, out: dict) -> AsyncIterator[str]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=config.DEEPSEEK_API_KEY,
                         base_url=config.DEEPSEEK_BASE_URL, timeout=60.0, max_retries=1)
    # Este endpoint SSE es exclusivamente el canal web (WhatsApp entra por
    # agent_core.run_agent) — la identidad de Sofía ya trae la framing "más
    # informativa, no insiste" incluida (ver agent_core.SYSTEM_PROMPT_WEB).
    system = SYSTEM_PROMPT_GERENTE if role == "gerente" else SYSTEM_PROMPT_WEB
    # Mismo bloque de conocimiento de gerencia que inyecta agent_core.run_agent
    # (los dos runners deben responder con la misma información del negocio).
    from .knowledge import knowledge_context
    system += await asyncio.to_thread(knowledge_context, tenant_id)
    if mem_ctx:
        system = f"{system}\n\n{mem_ctx}"
    hist_key = f"{tenant_id}:{session_id}"  # historial particionado por (tenant_id, sesión)
    history = await asyncio.to_thread(_load_history, hist_key)
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": message}]
    new_msgs: list[dict] = [{"role": "user", "content": message}]
    reply_text = ""

    for _round in range(MAX_TOOL_ROUNDS):
        mb = _MarkerBuffer()
        tool_calls: dict[int, dict] = {}
        stream = await client.chat.completions.create(
            model=config.DEEPSEEK_MODEL, messages=messages, tools=TOOLS_SCHEMA,
            temperature=0.6, max_tokens=900, stream=True)
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                emit = mb.push(delta.content)
                if emit:
                    yield _frame("token", {"text": emit})
            for tcd in (delta.tool_calls or []):
                slot = tool_calls.setdefault(tcd.index, {"id": None, "name": "", "arguments": ""})
                if tcd.id:
                    slot["id"] = tcd.id
                if tcd.function:
                    if tcd.function.name:
                        slot["name"] += tcd.function.name
                    if tcd.function.arguments:
                        slot["arguments"] += tcd.function.arguments

        tail = mb.finish()
        if tail:
            yield _frame("token", {"text": tail})

        if not tool_calls:
            reply_text = mb.full
            break

        ordered = sorted(tool_calls.items())
        tclist = [{"id": tc["id"] or f"call_{i}", "type": "function",
                   "function": {"name": tc["name"], "arguments": tc["arguments"] or "{}"}}
                  for i, tc in ordered]
        assistant_msg = {"role": "assistant", "content": mb.full or "", "tool_calls": tclist}
        messages.append(assistant_msg)
        new_msgs.append(assistant_msg)
        for i, tc in ordered:
            name = tc["name"]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield _frame("tool_start", {"tool": name, "args": args})
            try:
                result = await asyncio.to_thread(_exec_tool, name, args, phone=user_id,
                                                 role=role, tenant_id=tenant_id)
            except Exception as exc:  # una herramienta que falla no tumba el turno
                log.exception("tool %s falló", name)
                result = {"error": f"la herramienta falló: {exc}"}
            summary, meta = _summarize_tool(name, result)
            yield _frame("tool_result", {"tool": name, "summary": summary, "meta": meta})
            for f in _checkout_frames(name, result):
                yield f
            if (name not in _CHECKOUT_TOOLS and isinstance(result, dict)
                    and result.get("download_url")):
                yield _frame("document", {"download_url": result["download_url"],
                                          "title": "Cotización Tequendama"})
            tool_msg = {"role": "tool", "tool_call_id": tc["id"] or f"call_{i}",
                        "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]}
            messages.append(tool_msg)
            new_msgs.append(tool_msg)
    else:
        reply_text = reply_text or ("Estoy teniendo un problema técnico para completar "
                                    "esto. ¿Lo intentamos de nuevo?")

    quick_replies: list[str] = []
    m = SUGERENCIAS_RE.search(reply_text)
    if m:
        quick_replies = [s.strip() for s in m.group(1).split("|") if s.strip()][:3]
        reply_text = SUGERENCIAS_RE.sub("", reply_text).strip()
    if quick_replies:
        yield _frame("quick_replies", {"items": quick_replies})

    new_msgs.append({"role": "assistant", "content": reply_text})
    await asyncio.to_thread(_append_history, hist_key, new_msgs)
    out["reply"] = reply_text


# ---------- Runner demo (sin DEEPSEEK_API_KEY) ----------

def _norm(s: str) -> str:
    """minúsculas sin acentos (para matching robusto en español)."""
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn")


_TIPO_KEYWORDS = {
    "vida": ["vida"],
    "salud": ["salud", "medic", "eps", "enferm", "hospital"],
    "auto": ["auto", "carro", "vehiculo", "moto", "soat"],
    "hogar": ["hogar", "casa", "vivienda", "inmueble"],
    "viaje": ["viaje", "viajar", "turis", "vuelo"],
    "pyme": ["pyme", "negocio", "empresa", "emprend", "comercio"],
    "accidentes": ["accidente"],
    "exequial": ["exequial", "funerari", "sepelio", "velacion"],
    "mascotas": ["mascota", "perro", "gato", "veterinari"],
    "movilidad": ["bici", "patineta", "scooter", "cicla"],
}


def _parse_intent(message: str) -> tuple[str | None, str | None, int | None]:
    norm = _norm(message)
    tipo = next((t for t, kws in _TIPO_KEYWORDS.items() if any(k in norm for k in kws)), None)
    country = None
    for code, name in COUNTRY_NAMES.items():
        if _norm(name) in norm:
            country = code
            break
    if country is None:
        for code in COUNTRY_NAMES:
            if re.search(rf"\b{code.lower()}\b", norm):
                country = code
                break
    age = None
    m = re.search(r"(\d{1,2})\s*(?:anos?|years?)", norm) or re.search(r"\b(1[89]|[2-9]\d)\b", norm)
    if m:
        age = int(m.group(1))
    return country, tipo, age


async def _stream_text(text: str) -> AsyncIterator[str]:
    """Trocea un texto guía y lo emite token a token (palabra + espacio)."""
    for chunk in re.findall(r"\S+\s*|\s+", text):
        yield _frame("token", {"text": chunk})
        await asyncio.sleep(0.02)


def _format_options(country: str | None, ops: list[dict]) -> str:
    cname = COUNTRY_NAMES.get(country, country or "tu país")
    lines = [f"Estas son tus mejores opciones en {cname}:\n"]
    for i, o in enumerate(ops, 1):
        per = "por viaje" if o.get("periodicidad") == "por viaje" else "/mes"
        local = f"{o['prima_mensual_local']:,.0f} {o['moneda']}"
        usd = f"US${o['prima_mensual_usd']:,.2f}"
        cobs = ", ".join(o.get("coberturas", [])[:3])
        lines.append(f"{i}. {o['producto']} ({o['aseguradora']}) — {local}{per} ({usd}). "
                     f"Cubre: {cobs}.")
    return "\n".join(lines)


# ---------- Cierre autónomo en modo demo (sin DEEPSEEK_API_KEY) ----------

_CLOSE_KEYWORDS = (
    "contratar", "comprar", "cerrar", "adquirir", "emitir", "afiliarme", "afiliar",
    "lo quiero", "la quiero", "me la quedo", "la tomo", "lo tomo", "primera opcion",
    "segunda opcion", "tercera opcion", "quiero la primera", "quiero la segunda",
    "quiero la tercera", "quedar asegurad", "quiero esa", "quiero ese", "la primera",
    "quiero contratar", "quiero cerrar", "quiero asegurarme", "quedo asegurad",
)

_DOC_RE = re.compile(r"(?:cc|c\.c\.|cedula|c[eé]dula|documento|dni|nit|id)\s*[:#nºo°.\-]*\s*(\d{6,12})", re.I)
_NAME_RE = re.compile(
    r"(?:me llamo|mi nombre es|soy|mis datos son|datos son|nombre es|nombre:?)\s+"
    r"([A-Za-zÁÉÍÓÚÑáéíóúñ]+(?:\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]+){0,3})", re.I)


def _is_close_intent(message: str) -> bool:
    n = _norm(message)
    return any(k in n for k in _CLOSE_KEYWORDS)


def _parse_customer(message: str) -> tuple[str | None, str | None, bool]:
    """Extrae nombre, documento y consentimiento del texto libre del cliente."""
    raw = message or ""
    doc = None
    m = _DOC_RE.search(raw)
    if m:
        doc = m.group(1)
    else:
        m2 = re.search(r"\b(\d{7,12})\b", raw)
        if m2:
            doc = m2.group(1)
    name = None
    mn = _NAME_RE.search(raw)
    if mn:
        stop = {"cc", "c.c.", "cedula", "cédula", "documento", "dni", "nit", "id",
                "acepto", "autorizo", "y", "con", "el", "mi"}
        tokens = []
        for t in mn.group(1).split():
            if re.search(r"\d", t) or t.lower() in stop:
                break
            tokens.append(t)
        name = " ".join(tokens[:3]) or None
    n = _norm(raw)
    consent = bool(re.search(r"acepto|autorizo|si acepto|tratamiento de (mis )?datos|"
                             r"habeas data|de acuerdo|autoriz", n))
    return name, doc, consent


def _latest_quote_for(user_id: str) -> dict | None:
    """Última cotización del lead (por teléfono/user_id), con datos del producto."""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT q.*, p.nombre AS producto, p.tipo, p.aseguradora, p.coberturas
               FROM quotes q JOIN products p ON p.id = q.product_id
               JOIN leads l ON l.id = q.lead_id
               WHERE l.phone = %s ORDER BY q.id DESC LIMIT 1""",
            (user_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


async def _emit_checkout_tool(tool: str, args: dict, role: str, user_id: str,
                              tenant_id: str) -> tuple:
    """Ejecuta una herramienta de cierre y devuelve (result, [frames a emitir])."""
    frames = [_frame("tool_start", {"tool": tool, "args": args})]
    result = await asyncio.to_thread(_exec_tool, tool, args, phone=user_id, role=role,
                                     tenant_id=tenant_id)
    summary, meta = _summarize_tool(tool, result)
    frames.append(_frame("tool_result", {"tool": tool, "summary": summary, "meta": meta}))
    frames.extend(_checkout_frames(tool, result))
    return result, frames


async def _run_demo_close(session_id: str, message: str, role: str, user_id: str,
                          tenant_id: str, out: dict, quote: dict) -> AsyncIterator[str]:
    """Ejecuta el cierre REAL en modo demo: datos → consentimiento → emisión."""
    name, doc, _consent = _parse_customer(message)
    name = name or "Cliente Demo"
    doc = doc or "100000000"

    intro = ("¡Excelente decisión! Te dejo asegurada ahora mismo. Registro tus datos, "
             "confirmo tu autorización de datos y emito tu póliza...\n\n")
    async for f in _stream_text(intro):
        yield f

    cap_args = {"fullName": name, "document_id": doc}
    _, frames = await _emit_checkout_tool("capturar_datos_cliente", cap_args, role,
                                          user_id, tenant_id)
    for f in frames:
        yield f

    _, frames = await _emit_checkout_tool("registrar_consentimiento", {"acepta": True},
                                          role, user_id, tenant_id)
    for f in frames:
        yield f

    coberturas = []
    try:
        coberturas = json.loads(quote.get("coberturas") or "[]")
    except (json.JSONDecodeError, TypeError):
        coberturas = []
    coverage = {"aseguradora": quote.get("aseguradora"), "coberturas": coberturas,
                "resumen": f"{quote.get('producto')} ({quote.get('aseguradora')})"}
    emit_args = {"insurance_type": quote.get("tipo"),
                 "monthly_premium_cop": quote.get("premium_monthly_local"),
                 "coverage": coverage, "payment_method": "simulado"}
    emit, frames = await _emit_checkout_tool("emitir_poliza", emit_args, role,
                                             user_id, tenant_id)
    for f in frames:
        yield f

    if isinstance(emit, dict) and emit.get("policyNumber"):
        first = name.split()[0]
        closing = (f"¡Listo, {first}! Ya quedaste asegurada. Tu póliza es la "
                   f"N.º {emit['policyNumber']}, vigente por un año con {quote.get('aseguradora')}. "
                   f"Descarga tu certificado en el enlace de arriba. Recuerda que cuentas con "
                   f"derecho de retracto durante los 5 días hábiles siguientes.")
        if emit.get("degraded"):
            closing += ("\n\n(El registro central no respondió ahora mismo, así que tu "
                        "confirmación es provisional y quedará en firme enseguida.)")
        qr = ["Descargar mi póliza", "¿Qué cubre exactamente?", "Gracias"]
    else:
        err = emit.get("error") if isinstance(emit, dict) else "no pude completar la emisión"
        closing = f"Casi lo logramos, pero {err}. ¿Lo reintentamos?"
        qr = ["Reintentar", "Hablar con un asesor", "Ver mis datos"]
    async for f in _stream_text(closing):
        yield f
    out["reply"] = (intro + closing).strip()
    yield _frame("quick_replies", {"items": qr})
    await asyncio.to_thread(_append_history, f"{tenant_id}:{session_id}",
                            [{"role": "user", "content": message},
                             {"role": "assistant", "content": out["reply"]}])


async def _run_demo(session_id: str, message: str, mem_ctx: str, role: str,
                    user_id: str, tenant_id: str, out: dict) -> AsyncIterator[str]:
    # Cierre autónomo: si el cliente quiere comprar y ya hubo cotización, cierra de verdad.
    if role == "cliente" and _is_close_intent(message):
        quote = await asyncio.to_thread(_latest_quote_for, user_id)
        if quote:
            async for f in _run_demo_close(session_id, message, role, user_id,
                                           tenant_id, out, quote):
                yield f
            return

    country, tipo, age = _parse_intent(message)
    if country:
        intro = ("¡Con gusto te ayudo a proteger lo que más importa! Déjame calcular "
                 "unas opciones a tu medida, dame un segundo...\n\n")
        async for f in _stream_text(intro):
            yield f
        args: dict = {"country": country}
        if tipo:
            args["tipo"] = tipo
        if age:
            args["age"] = age
        yield _frame("tool_start", {"tool": "cotizar", "args": args})
        result = await asyncio.to_thread(_exec_tool, "cotizar", args, phone=user_id,
                                         role=role, tenant_id=tenant_id)
        ops = result.get("opciones") if isinstance(result, dict) else None
        if ops:
            summary, meta = _summarize_tool("cotizar", result)
            yield _frame("tool_result", {"tool": "cotizar", "summary": summary, "meta": meta})
            body = _format_options(country, ops)
            async for f in _stream_text(body):
                yield f
            top = ops[0]
            doc = await asyncio.to_thread(_exec_tool, "generar_documento",
                                          {"quote_id": top["quote_id"]}, phone=user_id,
                                          role=role, tenant_id=tenant_id)
            if isinstance(doc, dict) and doc.get("download_url"):
                d_summary, d_meta = _summarize_tool("generar_documento", doc)
                yield _frame("tool_result", {"tool": "generar_documento",
                                             "summary": d_summary, "meta": d_meta})
                yield _frame("document", {"download_url": doc["download_url"],
                                          "title": f"Cotización {top.get('producto', 'Tequendama')}"})
            closing = ("\n\nRecuerda que la emisión final de la póliza la realiza un asesor "
                       "licenciado. ¿Quieres que uno te contacte para cerrarla?")
            async for f in _stream_text(closing):
                yield f
            qr = ["Ver coberturas en detalle", "Prefiero otra opción", "Hablar con un asesor"]
            out["reply"] = (intro + body + closing).strip()
        else:
            msg = (result.get("mensaje") if isinstance(result, dict) else None) or \
                  "No encontré productos para ese caso. ¿Quieres que revise otro tipo de seguro?"
            yield _frame("tool_result", {"tool": "cotizar", "summary": "Sin opciones", "meta": {}})
            async for f in _stream_text(msg):
                yield f
            qr = ["Seguro de vida", "Seguro de salud", "Seguro de auto"]
            out["reply"] = (intro + msg).strip()
    else:
        if tipo:
            ask = (f"¡Hola! Soy Tequendama, tu asesora digital de seguros. Me encanta que "
                   f"pienses en un seguro de {tipo}. Para cotizarte a tu medida, cuéntame: "
                   f"¿en qué país estás y qué edad tienes?")
            qr = ["Estoy en Colombia", "Estoy en México", "Tengo 30 años"]
        else:
            ask = ("¡Hola! Soy Tequendama, tu asesora digital de seguros. Estoy aquí para "
                   "ayudarte a proteger lo que más importa. Para empezar, cuéntame: ¿qué te "
                   "gustaría asegurar y en qué país estás?")
            qr = ["Seguro de vida", "Seguro de salud", "Seguro de auto"]
        async for f in _stream_text(ask):
            yield f
        out["reply"] = ask

    yield _frame("quick_replies", {"items": qr})
    await asyncio.to_thread(_append_history, f"{tenant_id}:{session_id}",
                            [{"role": "user", "content": message},
                             {"role": "assistant", "content": out["reply"]}])


# ---------- Memoria del turno (best-effort) ----------

async def _remember(user_id: str, message: str, tenant_id: str) -> None:
    try:
        country, tipo, age = _parse_intent(message)
        if country:
            await memory.add_memory(user_id, f"El cliente está en {COUNTRY_NAMES.get(country, country)}", "perfil", tenant_id=tenant_id)
        if tipo:
            await memory.add_memory(user_id, f"El cliente tiene interés en seguro de {tipo}", "interes", tenant_id=tenant_id)
        if age:
            await memory.add_memory(user_id, f"El cliente tiene {age} años", "perfil", tenant_id=tenant_id)
        text = (message or "").strip()
        if text:
            await memory.add_memory(user_id, text[:200], "mensaje", tenant_id=tenant_id)
    except Exception:  # la memoria nunca debe romper el turno
        log.debug("no se pudo guardar memoria del turno", exc_info=True)


# ---------- Generador principal del stream ----------

async def _run_stream(req: StreamChatRequest, tenant_id: str, role: str) -> AsyncIterator[str]:
    session_id = req.session_id
    message = req.message or ""
    phone = (req.phone or "").strip()
    # El rol ya viene resuelto (JWT del login o fallback manager_key); un número de
    # WhatsApp autorizado sigue pudiendo elevar a gerente por compatibilidad.
    if role != "gerente" and phone and phone in MANAGER_PHONES:
        role = "gerente"
    # Identidad del turno: teléfono real > device_id (durable entre visitas y
    # conversaciones) > session_id (último recurso, muere con la conversación).
    user_id = phone or f"web:{req.device_id or session_id}"
    out: dict = {"reply": ""}
    try:
        yield _frame("thinking", {"text": "Analizando tu mensaje..."})
        await asyncio.to_thread(log_conversation, user_id, role, message, "web")
        # Fire-and-forget: nunca se espera (create_task, no await) para no
        # frenar el streaming SSE si el backend tarda o está caído.
        asyncio.create_task(asyncio.to_thread(
            backend_client.log_turn, tenant_id, user_id, "WEB_CHAT", role, message))
        mem_ctx = await memory.get_memory_context(user_id, tenant_id=tenant_id)

        runner = _run_llm if config.DEEPSEEK_API_KEY else _run_demo
        async for frame in runner(session_id, message, mem_ctx, role, user_id, tenant_id, out):
            yield frame

        if out.get("reply"):
            await asyncio.to_thread(log_conversation, user_id, "asistente", out["reply"], "web")
            asyncio.create_task(asyncio.to_thread(
                backend_client.log_turn, tenant_id, user_id, "WEB_CHAT", "asistente", out["reply"]))
        await _remember(user_id, message, tenant_id)
    except Exception as exc:  # cualquier fallo → frame de error, pero cerramos limpio
        log.exception("fallo en el stream del asistente")
        yield _frame("error", {"message": f"Ocurrió un problema técnico: {exc}"})
    yield _frame("done", {"session_id": session_id})


@router.post("/api/assistant/chat/stream")
async def assistant_chat_stream(
    req: StreamChatRequest,
    authorization: str = Header(default=""),
    x_tenant_id: str = Header(default="", alias="X-Tenant-Id"),
) -> StreamingResponse:
    """Turno conversacional por streaming SSE (contrato de FUSION.md).

    El tenant y el rol salen del JWT del login (`Authorization: Bearer <access>`):
    `tenant_id = claims.teamId`, `role` según `claims.role`. Sin token válido cae al
    header `X-Tenant-Id`/tenant demo y a `manager_key`. El estado del asistente se
    particiona por `(tenant_id, user_id)` y se propaga por toda la cadena."""
    tenant_id, role = resolve_identity(authorization, x_tenant_id, req.manager_key)
    return StreamingResponse(
        _run_stream(req, tenant_id, role), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                 "X-Accel-Buffering": "no"})
