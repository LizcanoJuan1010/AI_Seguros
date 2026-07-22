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
DB_PATH = Path(os.getenv("SEGURIA_DB", BASE_DIR.parent / "seguria.db"))
DOCS_DIR = Path(os.getenv("SEGURIA_DOCS_DIR", BASE_DIR.parent / "generated_docs"))

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

# LLM del orquestador web (DeepSeek u otro endpoint OpenAI-compatible)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Marca del documento de cotización
BRAND_NAME = os.getenv("BRAND_NAME", "SegurIA")
BRAND_TAGLINE = os.getenv("BRAND_TAGLINE", "Seguros a tu medida, en tu idioma")
BRAND_COLOR = os.getenv("BRAND_COLOR", "#0F4C81")

DOCS_DIR.mkdir(parents=True, exist_ok=True)
