# 🛡️ Tequendama — Plataforma de seguros con IA (Hackathon Colsubsidio 30X)

Asistente conversacional tipo **Erica (Bank of America)** que lleva a una persona de
_"no sé qué seguro necesito"_ a _"ya quedé asegurada"_ **sin hablar con nadie**: conversa
por web y **WhatsApp** (texto y voz), perfila, cotiza con FX real de 12 países LATAM,
**cobra con Polar**, **emite la póliza** con su PDF, y le da al gerente un panel con
KPIs, alertas y reportes por email.

> - Plan maestro: [docs/PLAN.md](docs/PLAN.md) · Fusión de arquitectura: [docs/FUSION.md](docs/FUSION.md)
> - Reto y cierre autónomo: [docs/RETO_COLSUBSIDIO.md](docs/RETO_COLSUBSIDIO.md)
> - Roadmap IA (paper McKinsey): [docs/ROADMAP_MCKINSEY.md](docs/ROADMAP_MCKINSEY.md)
> - Auditorías: [docs/AUDITORIA.md](docs/AUDITORIA.md)

## Arquitectura

```
Frontend React 19 (Tequendama, Vite + Tailwind v4)  :8090 (nginx)
   │  REST + SSE (rutas relativas /api/*)
   ├── /api/v1 → apps/backend   NestJS 11 + Prisma → Postgres   (dominio: CRM, checkout, pagos, dashboard)
   └── /api    → apps/ai        FastAPI (DeepSeek) → Postgres + Redis   (cerebro: chat SSE, cotizador, PDF, pagos Polar)
WhatsApp → Hermes Agent (7 skills) / Baileys bridge → misma API IA
Voz → Kokoro-FastAPI (TTS local)     Pagos → Polar (webhook → backend)
```

- El **backend NestJS** es el sistema de registro (Prisma posee el dominio en `public`).
- El **servicio IA** posee sus tablas en el esquema `seguria` del mismo Postgres y
  escribe el dominio a través de la API NestJS (`X-Tenant-Id` / JWT compartido).

## Features

### 🤖 Asistente conversacional (web `/asistente`)
- **Chat agéntico con streaming SSE** (`POST /api/assistant/chat/stream`): tokens en
  vivo, markdown, indicador "pensando", chips de herramientas (spinner → check),
  quick replies, cursor de escritura.
- **Orquestador propio** (`agent_core.py`): function calling multi-ronda (5) con
  DeepSeek y **23 herramientas** deterministas — el LLM jamás inventa precios ni
  documentos (redes de seguridad anti-"documento fantasma").
- **Voz en el chat web**: dictado por micrófono (Web Speech API) y respuestas
  habladas vía `/api/assistant/tts` (Kokoro local, perfil `voz`).
- **Modo demo sin API key**: el chat streamea, cotiza y cierra ventas reales aunque
  no haya `DEEPSEEK_API_KEY` (demoable siempre).
- **Memoria multi-tenant persistente** en Postgres, partición dura por
  `(tenant_id, usuario)`; historial de sesiones consultable desde la UI.
- **Subida de documentos al chat** (cédula, tarjeta de propiedad, RUT; PDF/imagen/
  Office, máx 10 MB) con extracción de texto (pdfplumber, OCR) y de campos
  (`analizar_documento`).

### 📋 Intake, perfilado y cotización
- **Intake data-driven** (`requisitos_seguros.json`): campos KYC/SARLAFT/underwriting
  por tipo de seguro, formularios estructurados en el chat y % de completitud.
- **Hiperperfilado determinista** (`profiling.py`): etapa de vida, segmento de
  riesgo, capacidad de pago, necesidades, propensión de compra y banderas de
  cumplimiento.
- **Cotizador determinista** (`quoting.py`): prima base × factor edad × factores de
  riesgo × suma asegurada, convertida a moneda local con **FX oficial de
  reguladores**; hasta 3 opciones comparadas.
- **Pricing personalizado por riesgo**: el segmento del perfil ajusta la prima
  (bajo −10% · alto +15%, acotado y explicado en el breakdown del chat y del
  PDF) — la prima refleja el riesgo real, no un promedio.
- **Catálogo real**: 24 productos, 10 tipos (vida, auto, salud, hogar, viaje, pyme,
  mascotas…), 14 aseguradoras, 12 países (CO, MX, PE, AR, CL, EC, PA, CR, DO, GT, UY, SV).

### ✅ Cierre autónomo (cotización → póliza, ≤8 turnos)
- Flujo completo en el chat: elegir opción → **captura de datos** → **consentimiento
  habeas data** (Ley 1581/2012, obligatorio y registrado) → **underwriting** →
  **pago** → **emisión**.
- **Underwriting semiautónomo** (`underwriting.py`): reglas deterministas y
  auditables deciden AUTO_APPROVE (emite sin humano), REFER (alerta al gerente
  en su panel, respuesta <24h) o DECLINE; la decisión queda registrada en
  `Quote.coverage.underwriting` y se muestra como tarjeta en el chat.
- `POST /api/v1/checkout` (NestJS, una transacción Prisma): upsert `Customer` →
  `Lead` (cerrado-ganado) → `Quote` (aceptada) → `Policy` **VIGENTE** con número
  `POL-2026-000NNN` y vigencia de 1 año.
- **UI de cierre en el chat**: stepper Datos → Consentimiento → Pago → Emisión,
  tarjeta de pago y tarjeta verde "¡Ya quedaste asegurada!" con PDF de la póliza.
- Derecho de retracto informado (Ley 1480/2011); takeover humano solo si el cliente lo pide.

### 💳 Pagos reales con Polar
- El servicio IA crea el **checkout de Polar** (sandbox) y entrega el link en el chat
  — la tarjeta nunca toca el chat ni el servidor (PCI del lado del gateway).
- **Webhook Standard Webhooks** en el backend (HMAC-SHA256, `timingSafeEqual`) con
  estados monotónicos (un webhook fuera de orden nunca regresa el estado).
- Herramientas del agente: `generar_link_pago`, `verificar_pago`,
  `solicitar_aclaracion` (reembolso/disputa). Modo simulado para demo.

### 📄 Documentos con marca
- **PDF de cotización y de póliza** (fpdf2) con identidad Tequendama: banda verde,
  regla ámbar, marca de agua, tablas zebra, caja legal y folio.
- Descarga directa desde el chat (`/api/documents/…`, con guardia anti path-traversal).
- **PPTX ejecutivos** por tipo de seguro vía OfficeCLI (skill de WhatsApp).

### 🩹 Reclamos / siniestros (FNOL)
- El cliente reporta por chat o WhatsApp ("chocaron mi carro"): la IA valida la
  póliza vigente, hace **triage determinista** con banderas de fraude
  (siniestro temprano, monto vs prima, reclamos previos — internas, nunca se
  muestran al cliente) y registra el reclamo `CLM-...` en el dominio.
- Tarjeta del reclamo en el chat con estado y **documentos de soporte por tipo**
  (data-driven, `requisitos_siniestros.json`); las fotos/PDF se suben por el
  mismo chat. Seguimiento con `estado_siniestro`.
- Módulo `claims` en el backend (CRUD tenant-scoped, `CLM-YYYY-000NNN`) y panel
  de reclamos con score de fraude en el dashboard del gerente.

### 📣 Motor proactivo (estilo Erica)
- Nudges por cliente: cotización sin respuesta, cierre pendiente, descubrimiento
  frío (`/api/proactive`), con límites anti-spam.
- **Renovaciones**: pólizas que vencen en ≤30 días generan nudge + alerta al
  gerente; la tool `proponer_renovacion` cotiza opciones frescas y cierra la
  renovación en el mismo chat.
- **Cross-sell**: detecta vacíos de protección (tiene auto y no vida) y lo
  sugiere una sola vez, según el perfil.
- Alertas de negocio para el gerente y cron de seguimiento por WhatsApp.

### 🔗 Seguro embebido (punto de compra, B2B2C)
- API **quote & bind** para aliados: `POST /api/embedded/quote` (prima al
  instante) y `POST /api/embedded/checkout` (emisión real en un paso, con el
  mismo underwriting del chat), auth por `PARTNER_API_KEYS`.
- Widget embebible `/embed` (iframe, sin login): un e-commerce agrega
  "protege tu compra" a su checkout en 2 clics.

### 📊 Panel gerencial (web `/gerente`)
- **KPIs del día** (llamadas IA, pólizas, ingresos COP, AHT), **rendimiento de
  agentes** (tabla + sparklines, vista SQL `v_agent_performance`), **alertas
  críticas**, ranking de ventas y banner de predicción IA.
- **Impacto IA** (`/api/v1/dashboard/ai-impact`): tiempo medio de cotización,
  % de pólizas emitidas sin humano, conversión lead→venta y tiempo de cierre —
  las métricas con las que el paper de McKinsey argumenta el retorno.
- **Panel de reclamos** con estado y score de fraude del triage; los REFER de
  underwriting llegan como alertas críticas.
- **Suscripciones a reportes por email** (diario/semanal/mensual, cliente o
  gerente): scheduler en background, HTML con marca, envío **SMTP con fallback
  Resend** (circuit breaker + throttle).
- **Insights por chat**: el gerente pregunta en lenguaje natural
  (`obtener_insights`, `listar_leads`) — KPIs, funnel, ventas por país/producto;
  enlaces a **Metabase** si está configurado.

### 🗂️ CRM / dominio (NestJS + Prisma, multi-tenant)
- Modelos: `Team`, `User`, `Customer`, `Product`, `Lead` (+`LeadEvent`), `Quote`,
  `Policy`, `Payment`, `Alert`, `AiCall` (+`CallMessage`) — enums de negocio en
  español, IDs UUID.
- **Multi-tenant por `Team`**: el `teamId` viaja en el JWT (o `X-Tenant-Id` para
  servicio-a-servicio); módulos scoped: customers, leads, quotes, policies,
  dashboard, checkout, payments.
- **Auth JWT** compartida entre backend y servicio IA (HS256, mismo `JWT_SECRET`):
  login con bcrypt, refresh tokens, roles AGENTE/GERENTE/ADMIN.
- CRUD completo: teams, users, products, ai-calls, call-messages, leads,
  lead-events, quotes, policies, alerts, customers.

### 💬 Canal WhatsApp (Hermes Agent) + 🎙️ voz
- **Persona Tequendama** (SOUL.md) con 8 skills: `asesor-seguros` (venta SPIN +
  objeciones), `documentos-cotizacion`, `insights-gerente` (con gating de rol por
  teléfono), `presentaciones-seguros` (PPTX), `seguimiento-proactivo` (cron),
  `siniestros` (FNOL por WhatsApp), `mercado-latam` (1.338 aseguradoras reales +
  FX), `voz`.
- **Voz**: notas de voz entrantes transcritas por Hermes (STT); respuestas como
  audio con **Kokoro-FastAPI** (TTS local en español, voz `ef_dora`).
- **Plan B de WhatsApp**: `baileys-bridge` (Node/Baileys, endpoints estilo
  Evolution API, multi-instancia con QR).

### 🌐 Frontend Tequendama (React 19 + Tailwind v4)
- **Landing** completa: hero con video de niebla + shader WebGL de agua, trust
  strip, 3 productos, "cómo funciona", insights con contadores animados,
  testimonios, FAQ, CTA band y footer.
- **Rutas por rol**: `/asistente` (chat), `/gerente` (dashboard), `/vendedor`
  (leads con filtros y drawer de detalle), `/llamada` (demo de llamada IA con orb
  visualizador).
- **Design system propio**: tokens Mist/Forest (`#083911` + ámbar `#ffbf00`) en
  `@theme`, tipografías Manrope/Sora/Fraunces, glassmorphism, `CountUp`, reveal
  animations; sin shadcn, sin alias `@/`.
- Login JWT con refresh automático y re-login en modal al expirar; selector de
  equipo (tenant); **fallback a datos mock** si el backend está caído.

### 🧱 Infra y calidad
- `docker-compose.yml`: postgres 16 + redis 7 + backend (3001) + IA (8085) +
  frontend nginx (8090); perfiles opcionales `voz` (Kokoro :8880), `hermes`,
  `baileys` (:8081).
- Suite pytest del servicio IA (13+ casos), auditoría adversarial aplicada (XSS,
  auth de endpoints con PII, WAL, timeouts, CORS configurable — ver
  [docs/AUDITORIA.md](docs/AUDITORIA.md)).
- Datos de referencia **reales y copiados** (nunca modificados en origen) en
  `data/market/`: aseguradoras canónicas de 10+ reguladores, FX oficial, catálogo,
  requisitos por tipo y base de conocimiento Colsubsidio.

## Arranque rápido

```bash
cp .env.example .env          # DEEPSEEK_API_KEY opcional (hay modo demo), Polar/SMTP opcionales
docker compose up -d --build  # postgres + redis + backend + IA + frontend
docker compose ps             # todos "Up"
# → http://localhost:8090   (login demo: gerente@colsubsidio.demo / demo123)
# → http://localhost:8085/api/health   (API IA)
# → http://localhost:3001/api/v1       (API dominio)
```

Perfiles opcionales: `docker compose --profile voz up -d` (TTS),
`--profile hermes` (WhatsApp), `--profile baileys` (bridge alterno).
Guía completa: [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md).

### Solo el servicio IA (sin Docker)

```bash
bash scripts/setup.sh api
cd apps/ai && .venv/bin/uvicorn app.main:app --port 8085
```

## Endpoints principales

| Servicio | Endpoint | Qué hace |
|---|---|---|
| IA | `POST /api/assistant/chat/stream` | Chat SSE (contrato en [docs/FUSION.md](docs/FUSION.md)) |
| IA | `POST /api/chat` | Turno agéntico síncrono (canal Hermes/WhatsApp) |
| IA | `POST /api/assistant/upload` | Subir documento del cliente |
| IA | `POST /api/quotes` · `POST /api/quotes/{id}/document` | Cotizar · PDF formal |
| IA | `GET /api/insights/summary` · `GET /api/proactive` | KPIs, nudges y renovaciones (gerente) |
| IA | `GET/POST/DELETE /api/reports/subscriptions` | Reportes por email |
| IA | `POST /api/embedded/quote` · `/api/embedded/checkout` | Seguro embebido para aliados |
| IA | `GET /api/assistant/tts` | Voz de la respuesta (Kokoro, perfil `voz`) |
| Backend | `POST /api/v1/auth/login` · `/refresh` · `GET /me` | Auth JWT |
| Backend | `POST /api/v1/checkout` | Emisión de póliza (transacción completa) |
| Backend | `POST /api/v1/payments/webhook` | Webhook Polar (firma verificada) |
| Backend | `GET /api/v1/dashboard/daily-kpis` · `/agent-performance` · `/ai-impact` | KPIs del panel |
| Backend | CRUD `/api/v1/{teams,users,customers,products,leads,quotes,policies,claims,alerts,ai-calls,…}` | Dominio |

## Estructura (monorepo polyglot)

```
apps/
  backend/            # NestJS 11 + Prisma — dominio multi-tenant → Postgres (host :3001)
  ai/                 # Python FastAPI — cerebro: chat SSE, tools, cotizador, PDF, Polar, email (:8085)
  frontend/           # React 19 + Vite + Tailwind v4 — landing + app por roles (nginx :8090)
  services/
    hermes-agent/     # workspace Hermes: SOUL.md, AGENTS.md, 7 skills — canal WhatsApp
    baileys-bridge/   # plan B WhatsApp (perfil docker "baileys")
data/market/          # aseguradoras LATAM + FX de reguladores + catálogo + requisitos (copiados)
deploy/               # nginx, Dockerfiles, systemd, DEPLOYMENT.md
docs/                 # PLAN, FUSION, AUDITORIA, RETO_COLSUBSIDIO, ROADMAP_MCKINSEY, AUTH, DDL
scripts/              # setup.sh, deploy_agent.sh
docker-compose.yml    # postgres + redis + backend + ai + frontend (+ perfiles voz/hermes/baileys)
```

## Cumplimiento

Tequendama **cierra la venta de forma autónoma**: Colsubsidio actúa como distribuidor y
la aseguradora emite. Antes de emitir se exige y registra el **consentimiento de
habeas data** (Ley 1581/2012); se divulgan aseguradora, coberturas, exclusiones y
prima; se informa el **derecho de retracto** (Ley 1480/2011); y el takeover humano
está disponible en cualquier momento si el cliente lo pide.
