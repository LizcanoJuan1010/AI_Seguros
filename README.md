# 🛡️ SegurIA — Asistente de IA para venta de seguros LATAM

Asistente conversacional tipo **Erica (Bank of America)** que vende seguros a la
medida por **WhatsApp** (texto y **voz**) en 12 países de LATAM, entrega
**cotizaciones en PDF** y **presentaciones PPTX**, y da **insights inteligentes**
(dashboards / Metabase) a los usuarios gerentes.

> Plan maestro y decisiones de arquitectura: [docs/PLAN.md](docs/PLAN.md)

## Arquitectura en una línea
**Hermes Agent** (persona + WhatsApp + memoria + skills, LLM DeepSeek) ⇄
**SegurIA API** (FastAPI: catálogo, cotizador con FX real, leads, PDF, insights) +
**OfficeCLI** (pptx) + **Voicebox** (TTS/STT local) + **SPA** (cotizador web + panel gerencial).

## Novedades (iteración SOTA)
- **`POST /api/chat`**: orquestador agéntico propio (function calling multi-ronda con
  DeepSeek) — la SPA ahora es un chat real con quick replies estilo Erica.
- **Motor proactivo** (`/api/proactive`): seguimientos por cliente y alertas de negocio;
  skill `seguimiento-proactivo` con cron y límites anti-spam.
- Venta consultiva SPIN + manejo de objeciones en la skill `asesor-seguros`.
- Detalles y auditoría: [docs/AUDITORIA.md](docs/AUDITORIA.md).

## Arranque rápido con Docker (todo el stack)
```bash
cp .env.example .env          # pon tu DEEPSEEK_API_KEY y MANAGER_PHONES
docker compose up -d --build  # API + TTS(voz) + agente Hermas + (opcional) Baileys
docker compose ps             # todos "Up"
# → http://localhost:8085  (SPA: pestañas "Asesor" y "Panel gerencial", key demo-gerente-2026)
```
Guía completa de despliegue y emparejamiento de WhatsApp: [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md).

## Solo el servicio IA (sin Docker)
```bash
bash scripts/setup.sh api
cd apps/ai && .venv/bin/uvicorn app.main:app --port 8085
```

## Agente por WhatsApp (nativo, sin Docker)
Sigue [services/hermes-agent/README.md](services/hermes-agent/README.md): configura DeepSeek
en `~/.hermes/`, arranca desde `services/hermes-agent/` para cargar la persona y las skills,
y empareja WhatsApp:

| Skill | Qué hace |
|---|---|
| `asesor-seguros` | Venta consultiva: descubre necesidad → cotiza vía API → 3 opciones |
| `documentos-cotizacion` | Genera y envía la cotización formal en PDF |
| `insights-gerente` | KPIs, funnel, ventas por país/producto, Metabase (solo rol gerente) |
| `presentaciones-seguros` | PPTX comerciales/ejecutivos con OfficeCLI |
| `voz` | Respuestas como nota de voz con Kokoro-FastAPI (TTS local en español) |
| `seguimiento-proactivo` | Nudges de seguimiento y alertas (estilo Erica) vía cron |
| `mercado-latam` | 1.338 aseguradoras reales + FX de reguladores (datos copiados) |

## Datos de referencia
`data/market/` contiene datos **copiados** (nunca modificados en origen) de
`latam-insurance-pipeline-kgm-main`: aseguradoras canónicas de 10+ reguladores y
tasas FX oficiales. Los módulos de referencia de Paloma (WhatsApp Cloud API,
docx builder, Metabase client) están en `apps/ai/app/reference/` y
`services/baileys-bridge/`.

## Estructura (monorepo polyglot)
```
apps/
  backend/      # NestJS + Prisma — dominio (leads, quotes, policies, checkout) → Postgres (3001)
  frontend/     # React 19 + Vite + Tailwind — SPA + chat /asistente (nginx :8090)
  ai/           # Python FastAPI — cerebro: chat SSE, cotizador, memoria, cierre/emisión, PDF (8085)
services/
  hermes-agent/     # workspace Hermes (SOUL.md, AGENTS.md, skills/) — canal WhatsApp
  baileys-bridge/   # plan B WhatsApp (perfil docker "baileys")
data/market/    # aseguradoras LATAM + FX (copiados de reguladores) + catálogo
deploy/         # nginx, Dockerfiles (frontend, hermes), systemd, DEPLOYMENT.md
docs/           # PLAN, FUSION, AUDITORIA, RETO_COLSUBSIDIO
scripts/        # setup.sh, deploy_agent.sh
docker-compose.yml   # postgres + redis + backend + ai + frontend (+ perfiles: voz/hermes/baileys)
```

## Cumplimiento
El asistente es un canal de **pre-venta**: informa, recomienda y cotiza; la emisión
final de la póliza la realiza un asesor licenciado en cada país (escalado humano
integrado). Los documentos lo indican expresamente.
