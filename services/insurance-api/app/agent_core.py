"""Orquestador agéntico de SegurIA: loop de function calling multi-ronda con DeepSeek.

Patrón tomado del orquestador de referencia (Paloma core/agents.py), reducido a lo
esencial y con sus dos lecciones clave:
  1. Las herramientas son la única fuente de precios/documentos (payloads
     estructurados y validados; el modelo nunca inventa cifras).
  2. Red de seguridad de documentos: si el modelo afirma haber enviado una
     cotización sin haber llamado la herramienta, se fuerza la corrección.

El canal principal (WhatsApp) lo orquesta Hermes con las skills; este módulo da la
misma capacidad agéntica al canal web (SPA) y sirve de fallback API-first.
"""
import json
import logging
import re
import sqlite3
from typing import Any

from .config import (DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
                     MANAGER_PHONES)
from .db import COUNTRY_NAMES, get_conn
from .documents import build_quote_pdf
from .insights import summary as insights_summary
from .quoting import recommend

log = logging.getLogger("seguria.agent")

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT_CLIENTE = """Eres SegurIA, asesora digital de seguros para Latinoamérica, al estilo de Erica de Bank of America: cercana, resolutiva y experta. Respondes en el idioma del cliente (español por defecto).

REGLAS DURAS:
- NUNCA des precios, primas ni coberturas de memoria: usa siempre la herramienta `cotizar` o `buscar_productos`. Si no has llamado la herramienta, no hay cifra.
- Descubre conversando (1-2 preguntas por mensaje, nunca un interrogatorio): país, edad, necesidad (vida|salud|auto|hogar|viaje|pyme|accidentes), a quién protege, presupuesto mensual.
- Presenta máximo 3 opciones, con prima en moneda local primero y USD entre paréntesis, y 2-3 coberturas clave por opción en lenguaje simple.
- Cuando el cliente elija una opción, llama `generar_documento` con su quote_id y entrega el enlace de descarga. Jamás digas que enviaste un documento sin haber llamado esa herramienta.
- Eres canal de PRE-VENTA: antes del cierre di siempre que la emisión final de la póliza la hace un asesor licenciado, y ofrece agendar esa llamada (herramienta `actualizar_lead` etapa "cerrado" si acepta).
- No pidas datos sensibles (historial médico detallado, tarjetas, contraseñas). No des consejo médico/legal/fiscal.
- Si el cliente se molesta o pide un humano: empatiza, llama `actualizar_lead` con etapa actual y di que un asesor lo contactará.
- Mensajes cortos tipo chat. Máximo un emoji por mensaje.

CONVERSACIÓN GUIADA: termina CADA respuesta con una última línea exacta:
SUGERENCIAS: opción 1 | opción 2 | opción 3
con 2-3 respuestas cortas que el cliente probablemente querría tocar (ej. "Seguro de vida | Para mi familia | Menos de $30/mes"). Esa línea no es parte del mensaje hablado."""

SYSTEM_PROMPT_GERENTE = """Eres SegurIA en modo analista para un GERENTE verificado del negocio de seguros. Estilo: analista de negocio senior, directo y accionable.

- Usa la herramienta `obtener_insights` para toda cifra (KPIs, funnel, países, productos, serie temporal). Nunca inventes datos.
- No vuelques JSON: responde la pregunta con 3-5 datos clave, una comparación relevante y UNA recomendación accionable.
- Tablas de texto simples para comparativas; números con separador de miles.
- Si pide seguimiento de leads usa `listar_leads`; si pide cambiar una etapa usa `actualizar_lead`.
- Termina cada respuesta con la línea:
SUGERENCIAS: pregunta 1 | pregunta 2
con 2 análisis de profundización que probablemente quiera (ej. "¿Dónde se caen los leads? | Compárame Colombia vs México")."""

TOOLS_SCHEMA = [
    {"type": "function", "function": {
        "name": "buscar_productos",
        "description": "Catálogo de productos de seguros disponibles, filtrable por país y tipo.",
        "parameters": {"type": "object", "properties": {
            "country": {"type": "string", "description": "Código ISO-2, ej. CO"},
            "tipo": {"type": "string", "enum": ["vida", "salud", "auto", "hogar", "viaje", "pyme", "accidentes"]},
        }}}},
    {"type": "function", "function": {
        "name": "cotizar",
        "description": "Cotiza seguros a la medida y devuelve hasta 3 opciones con quote_id, prima en moneda local y USD, y coberturas. Única fuente válida de precios.",
        "parameters": {"type": "object", "required": ["country"], "properties": {
            "country": {"type": "string", "description": "Código ISO-2 del país"},
            "tipo": {"type": "string", "enum": ["vida", "salud", "auto", "hogar", "viaje", "pyme", "accidentes"]},
            "age": {"type": "integer"},
            "name": {"type": "string", "description": "Nombre del cliente si lo dio"},
            "budget_monthly_usd": {"type": "number"},
            "sum_assured_usd": {"type": "number"},
            "extras": {"type": "object", "description": "fumador, dependientes, valor_bien_usd, dias_viaje, zona_alto_riesgo, preexistencias, destino_usa_europa...",
                       "properties": {}, "additionalProperties": True},
        }}}},
    {"type": "function", "function": {
        "name": "generar_documento",
        "description": "Genera la cotización formal en PDF de una opción ya cotizada. Devuelve la URL de descarga.",
        "parameters": {"type": "object", "required": ["quote_id"], "properties": {
            "quote_id": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "actualizar_lead",
        "description": "Actualiza los datos o la etapa del funnel del cliente (nuevo|descubrimiento|cotizado|documento|cerrado|perdido).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}, "country": {"type": "string"},
            "age": {"type": "integer"},
            "stage": {"type": "string", "enum": ["nuevo", "descubrimiento", "cotizado", "documento", "cerrado", "perdido"]},
        }}}},
    {"type": "function", "function": {
        "name": "obtener_insights",
        "description": "SOLO GERENTES: KPIs, funnel, ventas por país y producto, serie temporal.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "listar_leads",
        "description": "SOLO GERENTES: últimos leads con cotizaciones y prima.",
        "parameters": {"type": "object", "properties": {
            "limit": {"type": "integer", "default": 20}}}}},
]


def _exec_tool(name: str, args: dict, *, phone: str, role: str) -> Any:
    """Ejecuta una herramienta contra la lógica local (payload estructurado, validado)."""
    conn = get_conn()
    try:
        if name == "buscar_productos":
            rows = conn.execute("SELECT * FROM products").fetchall()
            out = []
            for r in rows:
                paises = json.loads(r["paises"])
                if args.get("country") and args["country"].upper() not in paises:
                    continue
                if args.get("tipo") and r["tipo"] != args["tipo"]:
                    continue
                out.append({"id": r["id"], "tipo": r["tipo"], "nombre": r["nombre"],
                            "aseguradora": r["aseguradora"],
                            "coberturas": json.loads(r["coberturas"])})
            return out or {"aviso": "sin productos con ese filtro; sugiere el tipo más cercano"}

        if name == "cotizar":
            if not args.get("country"):
                return {"error": "falta el país (country); pregúntaselo al cliente"}
            country = str(args["country"]).upper()
            if country not in COUNTRY_NAMES:
                return {"error": f"país no soportado: {country}", "soportados": list(COUNTRY_NAMES)}
            options = recommend(conn, country=country, tipo=args.get("tipo"),
                                age=args.get("age"), sum_assured_usd=args.get("sum_assured_usd"),
                                budget_monthly_usd=args.get("budget_monthly_usd"),
                                extras=args.get("extras") or {})
            from .main import _upsert_lead  # reusa el upsert canónico
            lead_id = _upsert_lead(conn, phone, args.get("name"), country, args.get("age"),
                                   stage="cotizado" if options else "descubrimiento")
            for o in options:
                cur = conn.execute(
                    """INSERT INTO quotes (lead_id, product_id, country, currency, sum_assured_usd,
                       premium_monthly_usd, premium_monthly_local, breakdown)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (lead_id, o["product_id"], country, o["moneda"], o["suma_asegurada_usd"],
                     o["prima_mensual_usd"], o["prima_mensual_local"],
                     json.dumps(o["breakdown"], ensure_ascii=False)))
                o["quote_id"] = cur.lastrowid
                o.pop("breakdown", None)
            conn.commit()
            return {"opciones": options}

        if name == "generar_documento":
            if not args.get("quote_id"):
                return {"error": "falta quote_id; cotiza primero y usa el quote_id de la opción elegida"}
            q = conn.execute(
                """SELECT q.*, p.nombre producto, p.tipo, p.aseguradora, p.coberturas, p.prima_por_dia
                   FROM quotes q JOIN products p ON p.id=q.product_id WHERE q.id=?""",
                (args["quote_id"],)).fetchone()
            if not q:
                return {"error": "quote_id no existe; cotiza primero"}
            lead = dict(conn.execute("SELECT * FROM leads WHERE id=?", (q["lead_id"],)).fetchone() or {}) if q["lead_id"] else None
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
            conn.execute("UPDATE quotes SET status='documento' WHERE id=?", (args["quote_id"],))
            if q["lead_id"]:
                conn.execute("UPDATE leads SET stage='documento', updated_at=datetime('now') "
                             "WHERE id=? AND stage NOT IN ('cerrado','perdido')", (q["lead_id"],))
            conn.commit()
            from pathlib import Path
            return {"download_url": f"/api/documents/{Path(path).name}",
                    "mensaje": "documento generado; entrega este enlace al cliente"}

        if name == "actualizar_lead":
            from .main import _upsert_lead
            lead_id = _upsert_lead(conn, phone, args.get("name"),
                                   (args.get("country") or "CO").upper(), args.get("age"),
                                   args.get("stage") or "descubrimiento")
            conn.commit()
            return {"ok": True, "lead_id": lead_id}

        if name == "obtener_insights":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            return insights_summary(conn)

        if name == "listar_leads":
            if role != "gerente":
                return {"error": "acceso denegado: solo gerentes"}
            rows = conn.execute(
                """SELECT l.name, l.country, l.stage, l.updated_at, COUNT(q.id) cotizaciones,
                          ROUND(COALESCE(SUM(q.premium_monthly_usd),0),2) prima_usd
                   FROM leads l LEFT JOIN quotes q ON q.lead_id=l.id
                   GROUP BY l.id ORDER BY l.updated_at DESC LIMIT ?""",
                (min(int(args.get("limit", 20)), 100),)).fetchall()
            return [dict(r) for r in rows]

        return {"error": f"herramienta desconocida: {name}"}
    finally:
        conn.close()


# ---------- Historial de sesión (SQLite) ----------

def _history_table(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        session_id TEXT, seq INTEGER, message TEXT,
        PRIMARY KEY (session_id, seq))""")


def _load_history(session_id: str, limit: int = 30) -> list[dict]:
    conn = get_conn()
    _history_table(conn)
    rows = conn.execute(
        "SELECT message FROM chat_history WHERE session_id=? ORDER BY seq DESC LIMIT ?",
        (session_id, limit)).fetchall()
    conn.close()
    msgs = [json.loads(r["message"]) for r in reversed(rows)]
    # La ventana no debe empezar con un 'tool' huérfano ni con un 'assistant' con
    # tool_calls cuyos 'tool' quedaron fuera: la API exige que cada 'tool' siga a su
    # 'assistant'+tool_calls. Recorta el prefijo hasta el primer 'user'.
    for i, m in enumerate(msgs):
        if m.get("role") == "user":
            return msgs[i:]
    return []


def _append_history(session_id: str, messages: list[dict]) -> None:
    conn = get_conn()
    _history_table(conn)
    row = conn.execute("SELECT COALESCE(MAX(seq),0) m FROM chat_history WHERE session_id=?",
                       (session_id,)).fetchone()
    seq = row["m"]
    for m in messages:
        seq += 1
        conn.execute("INSERT INTO chat_history (session_id, seq, message) VALUES (?,?,?)",
                     (session_id, seq, json.dumps(m, ensure_ascii=False)))
    conn.commit()
    conn.close()


# ---------- Loop principal ----------

SUGERENCIAS_RE = re.compile(r"\n?SUGERENCIAS:\s*(.+)\s*$", re.IGNORECASE)

DOC_CLAIM_RE = re.compile(r"(te (lo |la )?(envié|envío|mando|mandé)|adjunto|aquí tienes (el|tu) (pdf|documento|cotización))", re.IGNORECASE)


def run_agent(session_id: str, user_message: str, *, phone: str = "", role: str = "cliente") -> dict:
    """Un turno completo del agente: historial → LLM → herramientas (multi-ronda) → respuesta."""
    if not DEEPSEEK_API_KEY:
        return {"error": "llm_no_configurado",
                "reply": "El motor conversacional no está configurado (falta DEEPSEEK_API_KEY). "
                         "Puedes usar el cotizador rápido mientras tanto."}
    from openai import OpenAI
    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL,
                    timeout=30.0, max_retries=2)

    if not phone:
        phone = f"web:{session_id}"
    if role != "gerente" and phone in MANAGER_PHONES:
        role = "gerente"
    system = SYSTEM_PROMPT_GERENTE if role == "gerente" else SYSTEM_PROMPT_CLIENTE

    history = _load_history(session_id)
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": user_message}]
    new_msgs: list[dict] = [{"role": "user", "content": user_message}]
    actions: list[dict] = []
    tools_called: set[str] = set()

    reply = ""
    doc_claim_pending = False
    try:
        for _round in range(MAX_TOOL_ROUNDS):
            resp = client.chat.completions.create(
                model=DEEPSEEK_MODEL, messages=messages, tools=TOOLS_SCHEMA,
                temperature=0.6, max_tokens=900)
            msg = resp.choices[0].message
            if msg.tool_calls:
                assistant_msg = {"role": "assistant", "content": msg.content or "",
                                 "tool_calls": [tc.model_dump() for tc in msg.tool_calls]}
                messages.append(assistant_msg)
                new_msgs.append(assistant_msg)
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    log.info("tool %s(%s)", tc.function.name, args)
                    try:
                        result = _exec_tool(tc.function.name, args, phone=phone, role=role)
                    except Exception as exc:  # una herramienta que falla no tumba el turno
                        log.exception("tool %s falló", tc.function.name)
                        result = {"error": f"la herramienta falló: {exc}"}
                    tools_called.add(tc.function.name)
                    action = {"tool": tc.function.name, "args": args}
                    if isinstance(result, dict) and result.get("download_url"):
                        action["download_url"] = result["download_url"]
                    actions.append(action)
                    tool_msg = {"role": "tool", "tool_call_id": tc.id,
                                "content": json.dumps(result, ensure_ascii=False, default=str)[:6000]}
                    messages.append(tool_msg)
                    new_msgs.append(tool_msg)
                continue
            reply = msg.content or ""
            # Red de seguridad: afirma haber entregado un documento sin herramienta
            if DOC_CLAIM_RE.search(reply) and "generar_documento" not in tools_called and role == "cliente":
                doc_claim_pending = True
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content":
                                 "[sistema] Afirmaste entregar un documento sin generar ninguno. "
                                 "Llama la herramienta generar_documento con el quote_id correcto o corrige tu mensaje."})
                continue
            doc_claim_pending = False
            break
        else:
            reply = reply or "Estoy teniendo un problema técnico para completar esto. ¿Lo intentamos de nuevo?"
    except Exception as exc:  # error de red/API del LLM
        log.exception("fallo del LLM")
        return {"error": "llm_error", "reply":
                "Estoy teniendo un problema técnico en este momento. Intenta de nuevo en "
                "unos segundos, o usa el cotizador rápido mientras tanto.",
                "quick_replies": [], "actions": [], "role": role, "documents": []}

    # #8: si terminó afirmando un documento que nunca generó, no engañes al cliente
    if doc_claim_pending and "generar_documento" not in tools_called:
        reply = ("Puedo prepararte la cotización formal en PDF ahora mismo. "
                 "¿Confirmas la opción que te interesa para generarla?")

    quick_replies: list[str] = []
    m = SUGERENCIAS_RE.search(reply)
    if m:
        quick_replies = [s.strip() for s in m.group(1).split("|") if s.strip()][:3]
        reply = SUGERENCIAS_RE.sub("", reply).strip()

    new_msgs.append({"role": "assistant", "content": reply})
    _append_history(session_id, new_msgs)

    documents = [a["download_url"] for a in actions if a.get("download_url")]
    return {"reply": reply, "quick_replies": quick_replies, "actions": actions,
            "role": role, "documents": documents}
