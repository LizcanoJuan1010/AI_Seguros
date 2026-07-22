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

## Solo la API (sin Docker)
```bash
bash scripts/setup.sh api
cd services/insurance-api && .venv/bin/uvicorn app.main:app --port 8085
```

## Agente por WhatsApp (nativo, sin Docker)
Sigue [agent/README.md](agent/README.md): configura DeepSeek en `~/.hermes/`, arranca
desde `agent/` para cargar la persona y las 7 skills, y empareja WhatsApp:

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
docx builder, Metabase client) están en `services/insurance-api/app/reference/` y
`services/baileys-bridge/`.

## Estructura
```
agent/                    # workspace Hermes (SOUL.md, AGENTS.md, skills/)
services/insurance-api/   # FastAPI + SQLite + SPA + orquestador DeepSeek (8085) + tests
services/baileys-bridge/  # plan B WhatsApp (perfil docker "baileys")
data/market/              # aseguradoras LATAM + FX (copiados de reguladores)
deploy/                   # Dockerfile Hermes, DEPLOYMENT.md, systemd
docker-compose.yml        # stack completo: api + tts + hermes + baileys
docs/PLAN.md, AUDITORIA.md# plan maestro y auditoría
scripts/setup.sh          # instalación nativa por componente
```

## Cumplimiento
El asistente es un canal de **pre-venta**: informa, recomienda y cotiza; la emisión
final de la póliza la realiza un asesor licenciado en cada país (escalado humano
integrado). Los documentos lo indican expresamente.
