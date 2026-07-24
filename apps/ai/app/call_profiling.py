"""Perfilamiento de cliente a partir de la transcripción de una LLAMADA
(ElevenLabs). Cierra el hueco que el chat de WhatsApp/web no tiene: ahí el
propio DeepSeek va llamando `guardar_datos_cliente({campos})` mientras
conversa (ver `agent_core.py`); una llamada de voz corre en la
infraestructura de ElevenLabs, así que lo único que llega de vuelta es el
transcript crudo — este módulo corre ESA MISMA extracción, una sola vez,
sobre el transcript completo al terminar la llamada.

Reusa TAL CUAL el `intake_session` y `profiling.build_profile()` que ya usa
el chat (mismo `skey = f"{tenant_id}:{phone}"`) — no se inventa un modelo de
datos nuevo, el resultado es indistinguible de un perfil construido en vivo
por WhatsApp.
"""
import json
import logging

from . import profiling
from .agent_core import TOOLS_SCHEMA, _get_checkout, _get_intake, _save_intake
from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .db import get_conn

log = logging.getLogger("seguria.call_profiling")

_GUARDAR_DATOS_TOOL = next(
    t for t in TOOLS_SCHEMA if t["function"]["name"] == "guardar_datos_cliente")

# Instrucción crítica: estos campos alimentan underwriting/SARLAFT reales
# (salud, PEP, ingresos). Inventar uno que nunca se dijo no es un detalle
# cosmético, es un dato falso en un proceso de aseguramiento.
_EXTRACTION_SYSTEM_PROMPT = """Eres un extractor de datos, NO un vendedor. Vas a leer la transcripción de
una llamada telefónica de venta de seguros y debes llamar a la herramienta
`guardar_datos_cliente` UNA sola vez con los campos que el cliente
MENCIONÓ EXPLÍCITAMENTE (ocupación, ingresos, estado civil, dependientes,
fumador, enfermedades, vehículo, inmueble, negocio, viaje, etc.).

Reglas estrictas:
- NUNCA infieras ni completes un campo que no se dijo de forma explícita.
- Si el cliente no mencionó nada relevante, llama a la herramienta con
  campos={} (vacío) — eso es una respuesta válida y esperada.
- No repitas ni resumas la conversación, solo extrae datos estructurados.
- Usa los IDs de campo tal cual (ocupacion, ingresos_mensuales, fumador,
  estado_civil, dependientes, placa, tenencia, etc.), nunca inventes IDs
  nuevos."""


def _transcript_to_messages(transcript: list[dict]) -> list[dict]:
    """Convierte el transcript de ElevenLabs (`role` agent|user) al formato
    de mensajes OpenAI-compatible (assistant|user) que espera el chat."""
    messages = []
    for turn in transcript or []:
        role = "assistant" if turn.get("role") == "agent" else "user"
        content = (turn.get("message") or "").strip()
        if content:
            messages.append({"role": role, "content": content})
    return messages


def extract_fields_from_transcript(transcript: list[dict]) -> dict:
    """Corre la extracción LLM sobre el transcript completo. Devuelve `{}`
    sin credenciales, sin transcript útil, o ante cualquier error — nunca
    rompe el flujo del webhook que la llama (best-effort, igual que el
    resto del stack sin API keys)."""
    turns = _transcript_to_messages(transcript)
    if not DEEPSEEK_API_KEY or not turns:
        return {}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL,
                        timeout=30.0, max_retries=2)
        messages = [{"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                   {"role": "user", "content": "Transcripción de la llamada:"},
                   *turns]
        resp = client.chat.completions.create(
            model=DEEPSEEK_MODEL, messages=messages, tools=[_GUARDAR_DATOS_TOOL],
            tool_choice={"type": "function",
                        "function": {"name": "guardar_datos_cliente"}},
            temperature=0.1, max_tokens=600)
        tool_calls = resp.choices[0].message.tool_calls or []
        if not tool_calls:
            return {}
        args = json.loads(tool_calls[0].function.arguments or "{}")
        campos = args.get("campos") or {}
        return campos if isinstance(campos, dict) else {}
    except Exception as exc:
        log.warning("no se pudo extraer perfil del transcript: %s", exc)
        return {}


def _profile_table(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS customer_profile (
        phone TEXT PRIMARY KEY,
        perfil JSONB NOT NULL,
        fuente TEXT DEFAULT 'llamada',
        updated_at TIMESTAMPTZ DEFAULT now())""")


def _save_profile(conn, phone: str, perfil: dict, fuente: str = "llamada") -> None:
    _profile_table(conn)
    conn.execute(
        """INSERT INTO customer_profile (phone, perfil, fuente, updated_at)
           VALUES (%s,%s,%s,now())
           ON CONFLICT (phone) DO UPDATE SET
             perfil=excluded.perfil, fuente=excluded.fuente, updated_at=now()""",
        (phone, json.dumps(perfil, ensure_ascii=False), fuente))
    conn.commit()


def profile_from_call(tenant_id: str, phone: str, transcript: list[dict]) -> dict:
    """Extrae campos del transcript, los mezcla con lo que ya hubiera en el
    intake/checkout de ese (tenant, phone) — mismo `skey` que usa el chat —
    y construye el perfil con `profiling.build_profile` (reuso total, cero
    lógica de perfilamiento nueva). Persiste el resultado en
    `customer_profile` para que quede consultable."""
    skey = f"{tenant_id}:{phone}"
    campos = extract_fields_from_transcript(transcript)
    conn = get_conn()
    try:
        datos = _save_intake(conn, skey, campos) if campos else _get_intake(conn, skey)
        merged = {**datos, **_get_checkout(conn, skey)}
        perfil = profiling.build_profile(merged)
        _save_profile(conn, phone, perfil, fuente="llamada")
        return perfil
    finally:
        conn.close()
