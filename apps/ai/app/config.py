"""Configuración central de Tequendama API (variables de entorno con defaults de demo)."""
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
DATA_DIR = Path(os.getenv("SEGURIA_DATA_DIR", BASE_DIR.parent / "data" / "market"))
DOCS_DIR = Path(os.getenv("SEGURIA_DOCS_DIR", BASE_DIR.parent / "generated_docs"))
AUDIO_DIR = Path(os.getenv("SEGURIA_AUDIO_DIR", BASE_DIR.parent / "generated_audio"))

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

# LLM del orquestador web (DeepSeek u otro endpoint OpenAI-compatible).
# "deepseek-chat" quedó DEPRECADO por DeepSeek (confirmado jul 2026 contra
# la API real: devuelve 400 "The supported API model names are
# deepseek-v4-pro or deepseek-v4-flash") — cualquier .env que no
# sobreescriba DEEPSEEK_MODEL con un nombre viejo rompía TODAS las
# llamadas reales a DeepSeek (voz, chat web, WhatsApp), cayendo a demo o
# fallando. `-flash` es la variante rápida; `-pro` es más capaz pero más
# lenta, cambiar acá si hace falta más calidad que velocidad.
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Pasarela de pagos Polar: el access token vive SOLO en Nest
# (`POLAR_ACCESS_TOKEN` en apps/backend). Este proceso IA es cliente delgado
# de `POST /api/v1/payments/checkout` — no lee POLAR_* (deprecado en AI).

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

# Agente de PRUEBA para "Déjanos tu número y te llamamos" (landing_callback.py):
# mismo Camila/ElevenLabs, prompt distinto (informativo/venta de primer
# contacto, ver reference/elevenlabs_landing_test_prompt.md) — para no tocar
# el agente real de reactivación de checklist mientras se prueba. Vacío =
# usa ELEVENLABS_AGENT_ID (el mismo agente real) hasta que se configure uno
# de prueba aparte en el dashboard.
ELEVENLABS_LANDING_AGENT_ID = os.getenv("ELEVENLABS_LANDING_AGENT_ID", "") or ELEVENLABS_AGENT_ID

# Canal WhatsApp vía el gateway Baileys multi-tenant de Diache (reusado, no
# uno propio): un tenant nuevo ("tequendama") en ESE MISMO proceso ya
# desplegado. WA_GATEWAY_WEBHOOK_SECRET debe coincidir con el WEBHOOK_SECRET
# configurado allá — sin él, el receptor entrante rechaza todo con 401.
WA_GATEWAY_URL = os.getenv("WA_GATEWAY_URL", "")
WA_GATEWAY_WEBHOOK_SECRET = os.getenv("WA_GATEWAY_WEBHOOK_SECRET", "")
WA_GATEWAY_TENANT = os.getenv("WA_GATEWAY_TENANT", "tequendama")

# Número de WhatsApp del negocio (el ya emparejado con el gateway Baileys) que
# el chat WEB (Sofía) le ofrece al cliente cuando prefiere continuar por ahí
# con Mónica (ver agent_core._web_framing). Solo texto para mostrar, ej.
# "+57 300 000 0000".
WHATSAPP_BUSINESS_NUMBER = os.getenv("WHATSAPP_BUSINESS_NUMBER", "")

# URL pública donde vive ESTE servicio (seguria-ai), para construir links que
# el cliente pueda abrir de verdad fuera de la red interna: descarga de
# documentos por WhatsApp y el link de firma electrónica (ver esign.py). Sin
# esto configurado, esos links quedan como ruta relativa (rota fuera de la SPA).
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# Firma electrónica in-house (clickwrap): TTL del magic link.
ESIGN_LINK_TTL_MINUTES = int(os.getenv("ESIGN_LINK_TTL_MINUTES", "60"))

# KYC (Didit — verification.didit.me): documento de identidad + liveness +
# face match, capturados con cámara en vivo del navegador (link enviado por
# WhatsApp/correo, NUNCA fotos reenviadas del chat — ver investigación de esta
# sesión). Sin DIDIT_API_KEY corre en modo demo (mismo criterio que Polar/
# ElevenLabs): aprueba automático con datos simulados, para poder probar todo
# el flujo sin la key real.
DIDIT_API_KEY = os.getenv("DIDIT_API_KEY", "")
DIDIT_BASE_URL = os.getenv("DIDIT_BASE_URL", "https://verification.didit.me")
# Umbrales de decisión (0-100, ver docs.didit.me): por debajo de esto el caso
# pasa a revisión manual de un gerente en vez de aprobar automático.
DIDIT_LIVENESS_MIN_SCORE = int(os.getenv("DIDIT_LIVENESS_MIN_SCORE", "70"))
DIDIT_FACE_MATCH_MIN_SCORE = int(os.getenv("DIDIT_FACE_MATCH_MIN_SCORE", "70"))
KYC_LINK_TTL_MINUTES = int(os.getenv("KYC_LINK_TTL_MINUTES", "60"))

# Checklist de activación (ver app/checklist.py): a diferencia de KYC/esign/pago,
# el link del checklist NO vence — el cliente lo retoma cuando quiera. Horas sin
# avanzar de paso antes de que Camila (llamada saliente) reciba el aviso de
# reactivación (ver proactive.checklist_nudges).
CHECKLIST_STALL_HOURS = int(os.getenv("CHECKLIST_STALL_HOURS", "48"))

# URL pública del FRONTEND (apps/frontend, la SPA de React) — distinta de
# PUBLIC_BASE_URL (ese apunta a este servicio, seguria-ai). El checklist es una
# ruta de React (/activacion/{token}), no un endpoint de este FastAPI.
FRONTEND_PUBLIC_URL = os.getenv("FRONTEND_PUBLIC_URL", "").rstrip("/")

# Voz (Deepgram): tools de STT/TTS (voice_deepgram.py / deepgram-outbound) y
# la llamada en vivo /ws/voice/live (voice_live.py). Sin DEEPGRAM_API_KEY corre
# en modo demo (mismo criterio que el resto).
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
# `nova-3` (default, /v1/listen) vs `flux-general-multi` (/v2/listen,
# detección de turno SEMÁNTICA en vez de silencio — ver
# voice_live.DeepgramSTT.transcripts()). Cambiar de uno a otro es solo esta
# env var, sin tocar código — dejamos `nova-3` por defecto porque el
# comportamiento exacto de `transcript` en los eventos de Flux (¿acumulado
# por turno o incremental?) no se pudo verificar contra una llamada real en
# esta sesión; probarlo primero en un tenant/subset antes de activarlo global.
DEEPGRAM_STT_MODEL = os.getenv("DEEPGRAM_STT_MODEL", "nova-3")
# Preferí es-419 (LATAM) para la llamada en vivo; DEEPGRAM_LANGUAGE es el
# alias que usa voice_live.py (cae a DEEPGRAM_STT_LANGUAGE si no se setea).
# Con modelos flux-* se manda como `language_hint` (multilenguaje).
DEEPGRAM_STT_LANGUAGE = os.getenv("DEEPGRAM_STT_LANGUAGE", "es-419")
DEEPGRAM_LANGUAGE = os.getenv("DEEPGRAM_LANGUAGE", DEEPGRAM_STT_LANGUAGE)
# Silencio (ms) para cerrar la frase del usuario en /ws/voice/live con
# modelos nova-*; sin efecto con flux-* (la detección de turno es semántica).
# Más bajo = responde antes; demasiado bajo corta a mitad de frase.
DEEPGRAM_ENDPOINTING_MS = int(os.getenv("DEEPGRAM_ENDPOINTING_MS", "200"))
DEEPGRAM_VOICE_MODEL = os.getenv("DEEPGRAM_VOICE_MODEL", "aura-2-celeste-es")

# Motor de versionado/QA de prompts (docket-motor, adaptado — ver
# app/docket_engine/). Sin monitoreo en vivo (esa pieza del repo original es
# enterprise-only en ElevenLabs, descartada). Default False: sin esto, el
# proyecto sigue leyendo los prompts hardcodeados de agent_core.py, igual
# que siempre — cero riesgo para quien no lo active.
DOCKET_ENGINE_ENABLED = os.getenv("DOCKET_ENGINE_ENABLED", "false").lower() == "true"

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

# Marca de los documentos generados (cotización / certificado de póliza)
BRAND_NAME = os.getenv("BRAND_NAME", "Tequendama")
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "Protección inteligente inspirada en la naturaleza")
BRAND_COLOR = os.getenv("BRAND_COLOR", "#083911")  # verde primario del frontend
BRAND_ACCENT_COLOR = os.getenv("BRAND_ACCENT_COLOR", "#FFBF00")
BRAND_LOGO = Path(os.getenv("BRAND_LOGO", BASE_DIR / "assets" / "logo.png"))

DOCS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Estudio de banners de marketing (correo / Instagram / LinkedIn) generados con
# Gemini (familia "Nano Banana"). Default gemini-3.1-flash-image: mejor
# renderizado de texto que el 2.5 (pionero, ya legacy) — crítico porque el
# titular se escribe DENTRO de la imagen. gemini-3-pro-image es la opción
# premium (más lenta/cara) para banners con más texto o más detalle.
# Sin GEMINI_API_KEY el endpoint corre en modo demo (no genera nada, igual
# que el resto del stack sin keys).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
BANNERS_DIR = Path(os.getenv("SEGURIA_BANNERS_DIR", BASE_DIR.parent / "generated_banners"))
BANNERS_DIR.mkdir(parents=True, exist_ok=True)

# Paleta de marca de Colsubsidio (distribuidor), tomada de sus design tokens
# públicos (--color-blue/--color-yellow del CSS de colsubsidio.com) — para que
# los banners de campaña combinen con su sitio, no con el verde de Tequendama.
COLSUBSIDIO_PALETTE = {
    "azul": "#0067B1",
    "azul_fondo": "#F0F9F7",
    "amarillo": "#FFD000",
    "amarillo_claro": "#FFEC99",
    "amarillo_fondo": "#FFFDF4",
    "gris_texto": "#333333",
    "blanco": "#FFFFFF",
}

# Envío masivo de WhatsApp por campaña (ver campaign_broadcast.py). 8s fijos
# entre envíos: el gateway Baileys reusado NO es oficial (riesgo real de ban
# por detección de bulk, no un rate-limit de API como el de Resend en
# email_service.py) — ver docs/PLAN.md sobre "Baileys solo para demo".
CAMPAIGN_SEND_DELAY_SECONDS = int(os.getenv("CAMPAIGN_SEND_DELAY_SECONDS", "8"))
# Tope por llamada a /api/marketing/campaigns/broadcast (el backend NestJS ya
# rechaza segmentos más grandes antes de llegar acá; esto es una segunda
# barrera del lado del servicio que de verdad envía).
CAMPAIGN_BROADCAST_MAX = int(os.getenv("CAMPAIGN_BROADCAST_MAX", "300"))
