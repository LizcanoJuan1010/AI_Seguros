"""Configuración central de SegurIA API (variables de entorno con defaults de demo)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent.parent

# Carga .env de la raíz del repo si existe (no pisa variables ya exportadas)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
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
DATABASE_URL = os.getenv("DATABASE_URL", "")

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

# Backend NestJS (sistema de registro del dominio): expone POST /api/v1/checkout
# que crea Customer -> Lead -> Quote -> Policy y emite la póliza. El cierre autónomo
# del asistente llama a este servicio. Default apto para docker-compose.
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:3000")

# Marca del documento de cotización
BRAND_NAME = os.getenv("BRAND_NAME", "SegurIA")
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "Seguros a tu medida, en tu idioma")
BRAND_COLOR = os.getenv("BRAND_COLOR", "#0F4C81")

DOCS_DIR.mkdir(parents=True, exist_ok=True)
