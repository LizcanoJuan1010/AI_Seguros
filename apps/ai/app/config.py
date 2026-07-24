"""Configuración central de SegurIA API (variables de entorno con defaults de demo)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent.parent
BACKEND_ENV = PROJECT_ROOT / "apps" / "backend" / ".env"

# Carga .env de la raíz y del backend (no pisa variables ya exportadas).
# El backend guarda DATABASE_URL/DIRECT_URL; la raíz guarda claves de IA/JWT.
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(BACKEND_ENV, override=False)
except ImportError:
    pass
DATA_DIR = Path(os.getenv("SEGURIA_DATA_DIR", PROJECT_ROOT / "data" / "market"))
DOCS_DIR = Path(os.getenv("SEGURIA_DOCS_DIR", BASE_DIR.parent / "generated_docs"))

# NOTA: el servicio IA usa PostgreSQL EXCLUSIVAMENTE (cero SQLite). Todo el
# data-layer vive en el esquema `seguria` de la misma base que la memoria
# multi-tenant (ver DATABASE_URL abajo y app/db.py). `SEGURIA_DB`/`DB_PATH`
# quedaron OBSOLETOS y se eliminaron. El esquema es configurable vía
# `SEGURIA_DB_SCHEMA` (default `seguria`; la suite usa `seguria_test`).
DB_SCHEMA = os.getenv("SEGURIA_DB_SCHEMA", "seguria")


def _normalize_dsn(url: str) -> str:
    """Quita opciones solo de Prisma/pgbouncer que confunden a psycopg/asyncpg.

    `schema` (Prisma) y `pgbouncer` no son parámetros libpq válidos: dejarlos
    en la query string hace que psycopg.connect() falle con
    "invalid URI query parameter" (p.ej. al reusar DIRECT_URL de
    apps/backend/.env, que trae `?schema=public` para Prisma)."""
    from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

    parsed = urlparse(url.strip().strip("'\""))
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if k.lower() not in ("pgbouncer", "schema")]
    return urlunparse(parsed._replace(query=urlencode(query)))


def resolve_database_url() -> str:
    """Prefiere DIRECT_URL (sesión) para DDL; si no, DATABASE_URL."""
    raw = os.getenv("DIRECT_URL") or os.getenv("DATABASE_URL") or ""
    return _normalize_dsn(raw) if raw else ""

# Rol gerente: números de WhatsApp autorizados (separados por coma) y API key del panel
MANAGER_PHONES = {p.strip() for p in os.getenv("MANAGER_PHONES", "").split(",") if p.strip()}
MANAGER_API_KEY = os.getenv("MANAGER_API_KEY", "demo-gerente-2026")

# API key de servicio: la usan el agente (Hermes) y el backend para endpoints internos
# que manejan PII (roles, leads, conversaciones, seguimiento por cliente).
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "demo-service-2026")

# CORS: orígenes permitidos (coma-separados). La SPA es same-origin, así que el
# default no habilita ningún origen cruzado. Usa "*" solo en desarrollo.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

# Metabase (opcional): si hay credenciales, los insights enlazan dashboards reales
METABASE_URL = os.getenv("METABASE_URL", "")
METABASE_API_KEY = os.getenv("METABASE_API_KEY", "")

# Memoria multi-tenant (patrón Paloma): Postgres si está disponible, si no cae a
# un dict en proceso. Formato: postgresql://seguria:seguria@postgres:5432/seguria
# En local reutiliza apps/backend/.env (DIRECT_URL > DATABASE_URL).
DATABASE_URL = resolve_database_url()

# Multitenancy de dos ejes (patrón Paloma). El tenant se propaga por el header HTTP
# `X-Tenant-Id`; si falta se asume el tenant demo sembrado (Team.id demo del backend).
# La partición dura del asistente es `(tenant_id, user_id)`, nunca en estado global.
DEMO_TENANT_ID = os.getenv("DEMO_TENANT_ID", "11111111-1111-1111-1111-111111111111")

# JWT del login (patrón Paloma): el backend NestJS firma access tokens HS256 con esta
# misma clave; el servicio IA la usa para verificar `Authorization: Bearer <access>` y
# derivar tenant (`claims.teamId`) y rol (`claims.role`). Clave COMPARTIDA con el backend.
JWT_SECRET = os.getenv("JWT_SECRET", "demo-secret-seguria-2026")

# LLM del orquestador web (DeepSeek u otro endpoint OpenAI-compatible)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Pasarela de pagos Polar (polar.sh) — SANDBOX por defecto (sandbox-api.polar.sh).
# Token de organización (polar_oat_...) creado en el dashboard sandbox. Sin
# POLAR_ACCESS_TOKEN el flujo de pago corre en modo demo/simulado (igual que el
# resto del stack sin API keys). El backend valida el webhook con
# POLAR_WEBHOOK_SECRET (ver apps/backend). Nunca uses tokens prod en el hackathon.
POLAR_BASE_URL = os.getenv("POLAR_BASE_URL", "https://sandbox-api.polar.sh/v1")
POLAR_ACCESS_TOKEN = os.getenv("POLAR_ACCESS_TOKEN", "")
POLAR_SUCCESS_URL = os.getenv("POLAR_SUCCESS_URL", "")

# Motor de llamadas telefónicas — ElevenLabs Conversational AI (Agents Platform).
# Sin ELEVENLABS_API_KEY el motor corre en modo demo (igual que Wompi/DeepSeek):
# no llama a nadie, solo simula la respuesta. `ELEVENLABS_AGENT_PHONE_NUMBER_ID`
# es el número saliente configurado en el dashboard de ElevenLabs (Twilio o
# SIP trunk nativo); el mismo agente puede recibir el post-call webhook en
# apps/backend (ver ELEVENLABS_WEBHOOK_SECRET).
ELEVENLABS_BASE_URL = os.getenv("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID", "")
ELEVENLABS_AGENT_PHONE_NUMBER_ID = os.getenv("ELEVENLABS_AGENT_PHONE_NUMBER_ID", "")
# Voz específica (voice_id del dashboard de ElevenLabs). Vacío = usa la voz
# por defecto configurada en el agente; no hay una fija todavía.
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")

# Canal WhatsApp vía el gateway Baileys multi-tenant de Diache (reusado, no
# uno propio): un tenant nuevo ("tequendama") en ESE MISMO proceso ya
# desplegado. WA_GATEWAY_WEBHOOK_SECRET debe coincidir con el WEBHOOK_SECRET
# configurado allá — sin él, el receptor entrante rechaza todo con 401.
WA_GATEWAY_URL = os.getenv("WA_GATEWAY_URL", "")
WA_GATEWAY_WEBHOOK_SECRET = os.getenv("WA_GATEWAY_WEBHOOK_SECRET", "")
WA_GATEWAY_TENANT = os.getenv("WA_GATEWAY_TENANT", "tequendama")

# Backend NestJS (sistema de registro del dominio): expone POST /api/v1/checkout
# que crea Customer -> Lead -> Quote -> Policy y emite la póliza. El cierre autónomo
# del asistente llama a este servicio. Default apto para docker-compose.
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:3000")

# Seguro embebido (quote & bind para aliados B2B2C): API keys de partners
# separadas por coma. Cada aliado integra /api/embedded/* en su checkout.
PARTNER_API_KEYS = {k.strip() for k in
                    os.getenv("PARTNER_API_KEYS", "demo-partner-2026").split(",")
                    if k.strip()}

# TTS local (Kokoro-FastAPI del perfil `voz` del compose): el endpoint
# /api/assistant/tts lo proxya para no exponer el contenedor al navegador.
TTS_URL = os.getenv("TTS_URL", "http://seguria-tts:8880")
TTS_VOICE = os.getenv("TTS_VOICE", "ef_dora")

# Deepgram: STT/TTS en tiempo real para /ws/voice/live (LiveAiCallPage). Solo
# genera/transcribe voz — el agente sigue siendo agent_core.py (DeepSeek), no
# el Voice Agent de Deepgram. Sin DEEPGRAM_API_KEY el endpoint no puede abrir
# las conexiones a Deepgram (sin modo demo todavía, ver riesgos del diseño).
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
# Voz Aura-2 en español colombiano (acento del mercado de Tequendama).
DEEPGRAM_VOICE_MODEL = os.getenv("DEEPGRAM_VOICE_MODEL", "aura-2-celeste-es")

# Marca de los documentos generados (cotización / certificado de póliza)
BRAND_NAME = os.getenv("BRAND_NAME", "Tequendama")
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "Protección inteligente inspirada en la naturaleza")
BRAND_COLOR = os.getenv("BRAND_COLOR", "#083911")  # verde primario del frontend
BRAND_ACCENT_COLOR = os.getenv("BRAND_ACCENT_COLOR", "#FFBF00")
BRAND_LOGO = Path(os.getenv("BRAND_LOGO", BASE_DIR / "assets" / "logo.png"))

DOCS_DIR.mkdir(parents=True, exist_ok=True)
