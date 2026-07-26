# Tequendama — Asistente de IA para venta de seguros a la medida (LATAM)

> Plan maestro del proyecto. Hackathon Colsubsidio — julio 2026.
> Objetivo: un asistente tipo **Erica (Bank of America)** que conversa por **WhatsApp**
> (texto y voz), entiende la necesidad del cliente, recomienda y cotiza seguros a la
> medida por país, entrega documentos (cotización PDF/DOCX) y presentaciones (PPTX),
> y para usuarios **gerentes** entrega insights inteligentes (Metabase / dashboards).

---

## 1. Decisiones de arquitectura (con justificación)

| Componente | Elección | Por qué |
|---|---|---|
| Runtime del agente | **Hermes Agent** (NousResearch, MIT) | Pedido explícito. Trae gateway WhatsApp nativo, memoria persistente, skills, STT de notas de voz, cron, subagentes y MCP. Evita reconstruir orquestación. |
| LLM | **DeepSeek** (`api.deepseek.com`, API OpenAI-compatible) como primario; OpenRouter/Anthropic como alternos | Paloma ya lo validó en producción en español (deepseek-v4-flash/pro). Hermes soporta endpoints custom → conexión directa. Excelente costo/calidad para conversación de ventas. |
| Lógica de negocio | **`services/insurance-api`** (FastAPI + SQLite) propio | El catálogo de productos, el cotizador, los leads y los insights deben ser deterministas y auditables — no se dejan al LLM. El agente los consume como herramientas (HTTP). |
| WhatsApp | Gateway de Hermes (primario). Plan B: **baileys-bridge** de Paloma o **Meta Cloud API** (`whatsapp_official_client.py`) | Hermes lo trae integrado; los clientes de Paloma quedan copiados como respaldo productivo (Meta Cloud API = sin riesgo de ban). |
| Voz (TTS/STT) | **Voicebox** (local, REST `/generate` `/speak` `/transcribe`, MCP) con motores ligeros (Kokoro/Qwen3-TTS) para la RTX 3060 6GB. Alternativa de máxima calidad conversacional: **Sesame CSM-1B** (Apache 2.0, ~4.5GB VRAM) vía wrapper OpenAI-compatible | Local-first (datos de clientes no salen de la máquina), API simple, activo. Hermes ya transcribe notas de voz entrantes; Voicebox genera las respuestas de audio. |
| Documentos | `docx_builder.py` + `report_generator.py` (patrones de Paloma, adaptados) → cotizaciones DOCX/PDF con marca | Código probado; WeasyPrint/python-docx puro Python. |
| Presentaciones | **OfficeCLI** (iOfficeAI, Apache 2.0) vía CLI/MCP | Genera y edita .pptx reales por agente, con render a PNG para verificar. Una skill de Hermes lo orquesta por tipo de seguro. |
| Insights gerentes | Endpoints `/api/insights/*` (agregaciones SQL) + cliente **Metabase** REST (adaptado de `metabase_export.py` del pipeline LATAM) | Funciona sin depender de Metabase (demo) y se conecta a Metabase Cloud existente si hay credenciales. |
| Frontend | SPA ligera servida por la API (chat cliente + panel gerencial), inspirada en el diseño Stitch | El proyecto Stitch está tras login de Google; se replica la lógica (2 vistas por rol) y el look se ajusta luego con capturas/export del Stitch. |
| Datos de dominio | Copiados (nunca movidos) de `latam-insurance-pipeline-kgm-main` | 1.338 aseguradoras canónicas, tasas FX a USD, glosario de ramos → el agente habla con conocimiento real del mercado por país. |

## 2. Qué se reutiliza de cada fuente

### De `latam-insurance-pipeline-kgm-main` (COPIA, solo lectura)
- `app/data/entity_canonical_map.csv` → `data/market/aseguradoras_latam.csv` (1.338 aseguradoras, 10+ países).
- `app/data/fx_rates/fx_rates_fetched.csv`, `fx_rates_avg_fetched.csv` → `data/market/` (cotizar en moneda local).
- `METRIC_CATALOG` / ramos (vida, generales, salud, automóvil, incendio, transporte…) → vocabulario del catálogo de productos y prompts.
- `scripts/metabase_export.py` → base del cliente Metabase (`insights/metabase_client.py`).

### De `PalomaPresidentialAdministrativeComplete` (COPIA, solo lectura)
- `services/baileys-bridge/` → `services/baileys-bridge/` (plan B de WhatsApp).
- `clients/whatsapp_official_client.py` → Meta Cloud API para producción.
- `features/documents/docx_builder.py` → generador de cotizaciones DOCX con identidad de marca.
- `features/report_generator.py` (patrón Jinja2+WeasyPrint) → PDF de cotización/reportes.
- Patrones: memoria por `(agent_id, user_id)`, rate-limit + locks por teléfono + takeover humano del `whatsapp_handler.py`, auth JWT por roles.

### Repos externos
- **Hermes Agent** — runtime + WhatsApp + memoria + skills (`agent/` es su workspace).
- **OfficeCLI** — pptx/docx/xlsx por agente (skill `presentaciones-seguros`).
- **Voicebox** — TTS/STT local (skill `voz`).

## 3. Arquitectura del sistema

```
                          ┌────────────────────────────────┐
   Cliente WhatsApp ────► │  Hermes Agent (gateway WA)     │ ◄──── Gerente WhatsApp
   (texto / nota voz)     │  persona: SOUL.md (Tequendama) │       (rol por allowlist)
                          │  skills/ (6 skills)            │
                          └──────┬──────────┬──────────────┘
                                 │ HTTP     │ CLI/MCP
                 ┌───────────────▼───┐  ┌───▼────────────┐   ┌───────────────┐
                 │ insurance-api     │  │ OfficeCLI      │   │ Voicebox      │
                 │ (FastAPI+SQLite)  │  │ (.pptx/.docx)  │   │ (TTS/STT)     │
                 │ · catálogo        │  └────────────────┘   └───────────────┘
                 │ · cotizador+FX    │
                 │ · leads/quotes    │──► SPA: chat + panel gerencial
                 │ · documentos      │──► Metabase Cloud (opcional)
                 │ · insights        │
                 └───────────────────┘
```

### Flujo cliente (venta consultiva)
1. Cliente escribe/manda nota de voz por WhatsApp → Hermes transcribe (STT).
2. La skill `asesor-seguros` guía el descubrimiento: país, edad, dependientes, necesidad (vida/salud/auto/hogar/viaje/pyme), presupuesto.
3. Llama `POST /api/quotes` → cotizador determinista (tarifas por producto × factores de riesgo × FX a moneda local). Devuelve 2–3 opciones comparadas.
4. Cierre: `POST /api/quotes/{id}/document` genera la cotización formal (PDF/DOCX) y Hermes la envía por WhatsApp. Lead queda registrado con etapa del funnel.
5. Si el cliente lo pide (o mandó audio), la respuesta también va como nota de voz (Voicebox TTS).

### Flujo gerente
1. Número en `MANAGER_PHONES` (o login en la SPA con rol `gerente`) → skill `insights-gerente`.
2. Preguntas en lenguaje natural → `GET /api/insights/*` (ventas por país/producto, funnel, prima total, conversión) → respuesta con análisis del LLM + gráfico/tabla.
3. Con Metabase configurado: enlaces a dashboards y consultas a cards vía API.
4. `presentaciones-seguros`: genera PPTX ejecutivo por tipo de seguro con OfficeCLI.

## 4. Modelo de datos (SQLite `seguria.db`)
- `products` — id, tipo, nombre, aseguradora, países, prima_base_usd, factores (JSON), coberturas (JSON).
- `leads` — teléfono, nombre, país, edad, etapa funnel (`nuevo→descubrimiento→cotizado→documento→cerrado/perdido`), fuente.
- `quotes` — lead_id, product_id, suma asegurada, prima mensual local + USD, moneda, estado, breakdown JSON.
- `conversations` — registro por mensaje (canal, rol, texto) para insights.
- `fx_rates` — cargada desde los CSV copiados.

## 5. Estructura del repo

```
HackathonColsupcidio/
├── docs/PLAN.md                  # este documento
├── data/market/                  # datos copiados (aseguradoras, FX) + catalogo_productos.json
├── services/insurance-api/       # FastAPI: cotizador, leads, insights, documentos, SPA
├── services/baileys-bridge/      # copia de Paloma (plan B WhatsApp)
├── agent/                        # workspace Hermes: SOUL.md, AGENTS.md, skills/
├── frontend/                     # fuente de la SPA (se sirve desde la API)
├── scripts/setup.sh              # instala Hermes, OfficeCLI, deps, seeds
├── docker-compose.yml
└── .env.example
```

## 6. Fases de implementación
1. **F0 — Scaffolding + datos** ✅ estructura, git, copia de datos de referencia.
2. **F1 — insurance-api**: catálogo (≥12 productos, 6 tipos, 8 países), cotizador con FX, leads/quotes, seeds.
3. **F2 — Documentos**: cotización DOCX/PDF con marca.
4. **F3 — Insights**: agregaciones + cliente Metabase opcional.
5. **F4 — Workspace Hermes**: SOUL.md (persona Tequendama), 6 skills, config DeepSeek, guía de gateway WhatsApp y voz.
6. **F5 — Frontend**: SPA chat + panel gerencial (lógica Stitch).
7. **F6 — Infra**: docker-compose, setup.sh, README, pruebas end-to-end de la API.

## 7. Riesgos y mitigaciones
- **Stitch inaccesible** (login Google) → lógica replicada por contexto; pedir export/capturas para afinar estilos.
- **VRAM 6GB** → Voicebox con Kokoro/Qwen3-0.6B; CSM-1B solo si se libera VRAM.
- **Ban de WhatsApp con libs no oficiales** → para producción usar Meta Cloud API (cliente ya copiado); Baileys/gateway Hermes solo para demo.
- **Cumplimiento**: venta de seguros es actividad regulada por país → el agente se presenta como asistente de pre-venta que conecta con un asesor licenciado para el cierre (takeover humano, patrón de Paloma).
- **Metabase Cloud existente** pertenece a otro proyecto → los insights funcionan standalone; Metabase es opcional vía `.env`.
