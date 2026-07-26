<div align="center">
  <img src="apps/frontend/public/assets/logo.png" alt="Tequendama" width="140" />

  # Tequendama — Plataforma de seguros con IA

  **Hackathon Colsubsidio 30X**

  *De "no sé qué seguro necesito" a "ya quedé asegurada" — sin hablar con un humano.*

  Chat web · Llamada de voz en vivo · WhatsApp · Llamadas telefónicas salientes

  <br />

  <a href="https://www.youtube.com/watch?v=3NxcX0nJfu4">
    <img src="https://img.youtube.com/vi/3NxcX0nJfu4/maxresdefault.jpg" alt="▶️ Ver demo en YouTube" width="640" />
  </a>

  **[▶️ Ver la demo en YouTube](https://www.youtube.com/watch?v=3NxcX0nJfu4)**

</div>

---

Asistente conversacional tipo **Erica (Bank of America)** que conversa por **web,
voz en vivo y WhatsApp**, perfila, cotiza con FX real de 12 países LATAM,
**cobra con Polar**, verifica identidad (**KYC con Didit**), firma electrónica,
**emite la póliza** con su PDF, y le da al gerente un panel con KPIs, alertas,
campañas con IA y reportes por email.

> - Plan maestro: [docs/PLAN.md](docs/PLAN.md) · Fusión de arquitectura: [docs/FUSION.md](docs/FUSION.md)
> - Reto y cierre autónomo: [docs/RETO_COLSUBSIDIO.md](docs/RETO_COLSUBSIDIO.md)
> - Roadmap IA (paper McKinsey): [docs/ROADMAP_MCKINSEY.md](docs/ROADMAP_MCKINSEY.md)
> - Despliegue en Railway: [deploy/RAILWAY.md](deploy/RAILWAY.md) · Docker: [deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md)
> - Auditorías: [docs/AUDITORIA.md](docs/AUDITORIA.md)

## Arquitectura

```
Frontend React 19 (Vite + Tailwind v4)  :8090 (nginx)
   │  REST + SSE + WebSocket (rutas relativas /api/*)
   ├── /api/v1 → apps/backend   NestJS 11 + Prisma → Postgres   (dominio: CRM, checkout, pagos, dashboard)
   │      └── WS /api/v1/live-call → relay hacia el servicio IA (llamada de voz en vivo)
   └── /api    → apps/ai        FastAPI (DeepSeek) → Postgres + Redis   (cerebro: chat SSE, tools, cotizador, PDF)
                     └── WS /ws/voice/live → Deepgram Voice Agent (STT+TTS) con "think" = DeepSeek

WhatsApp → Hermes Agent (skills) / Baileys bridge → misma API IA
Llamada saliente al celular → ElevenLabs Conversational AI (webhook post-call → backend)
Voz del chat → Kokoro-FastAPI (TTS local)     Pagos → Polar (webhook firmado → backend)
Correo → SMTP con fallback automático a Resend (circuit breaker + throttle)
```

- El **backend NestJS** es el sistema de registro (Prisma posee el dominio en `public`).
- El **servicio IA** posee sus tablas en el esquema `seguria` del mismo Postgres y
  escribe el dominio a través de la API NestJS (`X-Tenant-Id` / JWT compartido).

## Los cuatro canales del agente

| Canal | Persona | Cómo entra el cliente |
|---|---|---|
| 💬 Chat web (`/asistente`) | Sofía — informativa, streaming SSE | Sin login (identidad `device_id` del navegador) |
| 📞 **Llamada de voz en vivo** (`/llamada`) | Voz en tiempo real (Deepgram Voice Agent + DeepSeek) | Sin login; micrófono del navegador |
| 📱 WhatsApp | Mónica — el canal de cierre | Gateway Hermes/Baileys |
| ☎️ Llamada saliente al celular | Camila (ElevenLabs) | "Déjanos tu número" en la landing, o el CRM |

## Features

### 📞 Llamada de voz EN VIVO desde el navegador (`/llamada`)
- **Conversación hablada real** con el agente: STT + TTS de **Deepgram Voice Agent**
  con el "cerebro" (`think`) enrutado a **DeepSeek** vía endpoint custom — mismas
  herramientas y lógica de negocio que el chat.
- Cadena WebSocket completa: navegador → nginx → **gateway WS de NestJS**
  (`/api/v1/live-call`, con heartbeat ping/pong y timeouts) → FastAPI
  (`/ws/voice/live`) → Deepgram.
- **Sin login**: el cliente anónimo entra con su `device_id` (misma identidad que
  ancla su memoria del chat); topes anti-abuso (1 llamada simultánea por
  dispositivo, 25 globales). El staff entra con su JWT.
- **Barge-in** (interrumpir a la IA hablando), cards en pantalla con resultados de
  herramientas, tarjeta de pago, número de póliza al emitir; keepalive de silencio
  (silenciar el mic no mata la llamada); transcript persistido en el CRM
  (`AiCall` canal `WEB_VOICE_CALL`).
- UX robusta: F5 y reentrar funcionan; errores visibles con botón "Volver a
  llamar"; al colgar, disolución y regreso al chat.
- Requiere `DEEPGRAM_API_KEY` **y** `DEEPSEEK_API_KEY` (sin modo demo).

### 📲 "Déjanos tu número y te llamamos" (landing)
- Formulario público en el inicio: nombre + celular + ramo de interés +
  consentimiento (Ley 1581/2012) → el sistema **llama al celular** con el agente
  de voz de **ElevenLabs** (ficha PDF previa por WhatsApp).
- Capa anti-abuso (`callback.py`): normalización E.164 colombiana, rechazo de
  fijos, topes por hora (teléfono/dispositivo/IP) y rastro auditable del
  consentimiento en `callback_request`.
- El resultado de la llamada vuelve por el **webhook post-call** (idempotente) al
  backend: `AiCall` + `CallMessage` + perfilado automático.

### 🤖 Asistente conversacional (web `/asistente`)
- **Chat agéntico con streaming SSE**: tokens en vivo, markdown, indicador
  "pensando", chips de herramientas, quick replies.
- **Orquestador propio** (`agent_core.py`): function calling multi-ronda con
  DeepSeek y **33 herramientas** deterministas — el LLM jamás inventa precios ni
  documentos (verificado en vivo: los precios coinciden al peso con el motor).
- **Memoria multi-tenant persistente** en Postgres, partición por
  `(tenant_id, usuario)`; el `device_id` anónimo ancla memoria y leads entre
  visitas — sin registro.
- **Subida de documentos** (PDF/imagen/Office, máx 10 MB) con extracción de campos.
- **Modo demo sin API key**: el chat streamea y cotiza aunque no haya
  `DEEPSEEK_API_KEY`.

### ✅ Cierre autónomo (cotización → póliza)
- Flujo completo: elegir opción → **captura de datos** → **consentimiento habeas
  data** (Ley 1581/2012) → **KYC de identidad con Didit** (cédula + selfie +
  prueba de vida, por link con la cámara del celular) → **firma electrónica**
  in-house (clickwrap, Ley 527/1999) → **underwriting** → **pago** → **emisión**.
- **Checklist de activación autogestionado**: link único
  (`/activacion/<token>`, no vence) por WhatsApp/correo donde el cliente
  completa identidad → firma → pago a su ritmo; con reactivación telefónica
  (Camila llama a quien lo dejó a medias).
- **Underwriting semiautónomo**: AUTO_APPROVE emite sin humano; REFER alerta al
  gerente (<24h); DECLINE con alternativas. Todo registrado y auditable.
- `POST /api/v1/checkout` (una transacción Prisma): `Customer` → `Lead` →
  `Quote` → `Policy` **VIGENTE** con número `POL-2026-000NNN`.
- Derecho de retracto informado (Ley 1480/2011); takeover humano si el cliente lo pide.

### 📋 Intake, perfilado y cotización
- **Intake data-driven** (`requisitos_seguros.json`): campos KYC/SARLAFT por tipo
  de seguro, formularios estructurados y % de completitud.
- **Hiperperfilado determinista** (`profiling.py`): etapa de vida, segmento de
  riesgo, capacidad de pago, propensión y banderas.
- **Cotizador determinista** (`quoting.py`) con **FX oficial de reguladores**;
  pricing personalizado por riesgo (acotado y explicado en el breakdown).
- **Catálogo real**: 20+ productos, 10 tipos, 14 aseguradoras, 12 países
  (CO, MX, PE, AR, CL, EC, PA, CR, DO, GT, UY, SV), editable por gerencia
  desde el panel (los precios editados a mano sobreviven a los reinicios).

### 💳 Pagos reales con Polar
- El backend NestJS es el único dueño del token: crea el **checkout de Polar**
  (sandbox) y el link viaja al chat/llamada — la tarjeta nunca toca el sistema.
- **Webhook Standard Webhooks** (HMAC-SHA256, `timingSafeEqual`) con estados
  monotónicos. Herramientas: `generar_link_pago`, `verificar_pago`,
  `solicitar_aclaracion` (reembolso/disputa). Modo simulado para demo.

### 📄 Documentos con marca
- **PDF de cotización y de póliza** (fpdf2) con identidad Tequendama; descarga
  directa desde el chat con guardia anti path-traversal.
- **PPTX ejecutivos** por tipo de seguro (skill de WhatsApp).

### 🩹 Reclamos / siniestros (FNOL)
- Reporte por chat o WhatsApp: validación de póliza vigente, **triage
  determinista** con banderas de fraude (internas), reclamo `CLM-...` en el
  dominio, documentos de soporte data-driven y seguimiento.

### 📣 Motor proactivo + campañas
- Nudges por cliente (cotización sin respuesta, cierre pendiente), renovaciones
  (≤30 días) y cross-sell según perfil, con límites anti-spam.
- **Campañas de marketing** (`/campanas`, solo GERENTE/ADMIN): banners generados
  con **Gemini** (paleta Colsubsidio) y envío segmentado por temperatura de lead.
- **Reactivación telefónica de checklists** a medias (Camila/ElevenLabs).

### 🔗 Seguro embebido (B2B2C)
- API **quote & bind** para aliados (`/api/embedded/*`, auth por
  `PARTNER_API_KEYS`) y widget `/embed` (iframe sin login).

### 📊 Panel gerencial (web `/gerente`)
- **KPIs del día en vivo**, rendimiento de agentes, alertas críticas (incluidos
  los REFER de underwriting), ranking de combos, panel de reclamos con score de
  fraude, adquisición por red social.
- **Cliente 360**: expediente completo con cruce dominio ↔ IA (perfil, llamadas,
  documentos, afiliación Colsubsidio).
- **Panel "Agente IA"**: gerencia edita precios y conocimiento del agente (se
  inyecta al prompt de todas las conversaciones) + muro de ideas de producto.
- **Reportes por email** (diario/semanal/mensual) con scheduler en background —
  envío **SMTP con fallback automático a Resend** (circuit breaker + throttle;
  los fallos se loguean con motivo y se reintentan, nunca se pierden en silencio).
- **Insights por chat** en lenguaje natural; enlaces a Metabase si está configurado.

### 🗂️ CRM / dominio (NestJS + Prisma, multi-tenant)
- Modelos: `Team`, `User`, `Customer` (+`CustomerDocument`), `Insurer`, `Product`,
  `Lead` (+`LeadEvent`), `Quote`, `Policy`, `Payment`, `Claim`, `Alert`,
  `AiCall` (+`CallMessage`), `Campaign` (+`CampaignSend`).
- **Multi-tenant por `Team`** (`teamId` en el JWT o `X-Tenant-Id`
  servicio-a-servicio); **Auth JWT** compartida backend ↔ IA (HS256), roles
  AGENTE/GERENTE/ADMIN, refresh tokens.

### 💬 Canal WhatsApp (Hermes Agent) + 🎙️ voz
- **Persona Mónica** (SOUL.md) con skills: venta SPIN, documentos, insights de
  gerente (gating por teléfono), PPTX, seguimiento proactivo (cron), siniestros,
  mercado LATAM (1.338 aseguradoras reales + FX), notas de voz (Deepgram STT/TTS).
- **Plan B de WhatsApp**: `baileys-bridge` (gateway propio multi-instancia con QR).

### 🌐 Frontend (React 19 + Tailwind v4)
- **Landing** completa: hero con video, productos, cómo funciona, **"Déjanos tu
  número y te llamamos"**, insights animados, testimonios, FAQ, CTA.
- Rutas: `/asistente` (chat, pública) · `/llamada` (voz en vivo, pública) ·
  `/activacion/:token` (checklist del cliente) · `/gerente` y `/campanas`
  (staff) · `/embed` (aliados).
- **Design system propio**: tokens Mist/Forest (`#083911` + ámbar `#ffbf00`),
  Manrope/Sora/Fraunces, glassmorphism; sin shadcn, sin alias `@/`.

### 🧱 Infra y calidad
- `docker-compose.yml`: postgres 16 (pgvector) + redis 7 + backend (3001) +
  IA (8085) + frontend nginx (8090, con `resolver` de Docker para sobrevivir
  redeploys); perfiles opcionales `voz`, `hermes`, `baileys`, `voice-outbound`.
- **Suites**: 88 tests del servicio IA + 29 del backend; batería E2E de navegador
  (landing, chat, ciclo completo de llamada, dashboard) y sondeo en vivo contra
  la API real de Deepgram — todo en verde.
- Despliegue a producción documentado paso a paso en
  [deploy/RAILWAY.md](deploy/RAILWAY.md) (variables por servicio, trampas de
  webhooks, disco efímero, réplicas).
- Datos de referencia **reales** en `data/market/`: aseguradoras de 10+
  reguladores, FX oficial, catálogo y base de conocimiento Colsubsidio.

## Arranque rápido

```bash
cp .env.example .env          # ver notas dentro: qué es opcional y qué no
docker compose up -d --build  # postgres + redis + backend + IA + frontend
docker compose ps             # todos "Up"
# → http://localhost:8090             (login staff demo: gerente@colsubsidio.demo / demo123)
# → http://localhost:8090/llamada     (llamada de voz en vivo — requiere las 2 keys de abajo)
# → http://localhost:8085/api/health  (API IA)
# → http://localhost:3001/api/v1      (API dominio)
```

**Claves mínimas por funcionalidad** (todo lo demás degrada a modo demo):

| Funcionalidad | Variables |
|---|---|
| Chat con LLM real | `DEEPSEEK_API_KEY` |
| **Llamada de voz en vivo** (sin modo demo) | `DEEPSEEK_API_KEY` + `DEEPGRAM_API_KEY` |
| Correo (informes, links de firma/KYC/activación) | `RESEND_API_KEY` + `RESEND_FROM_EMAIL` (dominio verificado) |
| Links de activación que abran fuera de la SPA | `FRONTEND_PUBLIC_URL` |
| Llamadas salientes al celular | `ELEVENLABS_API_KEY` + `_AGENT_ID` + `_AGENT_PHONE_NUMBER_ID` |
| Pagos reales | `POLAR_ACCESS_TOKEN` + `POLAR_WEBHOOK_SECRET` (los 4 `POLAR_*`) |
| KYC real | `DIDIT_API_KEY` |

Perfiles opcionales: `docker compose --profile voz up -d` (TTS Kokoro),
`--profile hermes` (WhatsApp), `--profile baileys`, `--profile voice-outbound`.

### Solo el servicio IA (sin Docker)

```bash
bash scripts/setup.sh api
cd apps/ai && .venv/bin/uvicorn app.main:app --port 8085
```

## Endpoints principales

| Servicio | Endpoint | Qué hace |
|---|---|---|
| IA | `POST /api/assistant/chat/stream` | Chat SSE (contrato en [docs/FUSION.md](docs/FUSION.md)) |
| IA | `WS /ws/voice/live` | Llamada de voz en vivo (lo consume el gateway de Nest) |
| IA | `POST /api/callback/solicitar` | "Déjanos tu número" (público, con anti-abuso) |
| IA | `POST /api/chat` | Turno agéntico síncrono (canal Hermes/WhatsApp) |
| IA | `GET /api/checklist/{token}` · `POST …/avanzar` | Checklist de activación del cliente |
| IA | `GET /kyc/{token}` · `GET /sign/{token}` | KYC Didit · firma electrónica |
| IA | `POST /api/quotes` · `POST /api/quotes/{id}/document` | Cotizar · PDF formal |
| IA | `POST /api/calls/outbound` | Llamada saliente ElevenLabs (servicio/CRM) |
| IA | `GET /api/insights/summary` · `GET /api/proactive` | KPIs, nudges y renovaciones (gerente) |
| IA | `GET/POST/DELETE /api/reports/subscriptions` | Reportes por email |
| IA | `POST /api/embedded/quote` · `/api/embedded/checkout` | Seguro embebido para aliados |
| Backend | `WS /api/v1/live-call` | Gateway de la llamada en vivo (JWT o `device_id`) |
| Backend | `POST /api/v1/auth/login` · `/refresh` · `GET /me` | Auth JWT |
| Backend | `POST /api/v1/checkout` | Emisión de póliza (transacción completa) |
| Backend | `POST /api/v1/payments/webhook` · `/api/v1/elevenlabs/webhook` | Webhooks firmados (Polar · post-call) |
| Backend | `GET /api/v1/dashboard/daily-kpis` · `/agent-performance` · `/ai-impact` | KPIs del panel |
| Backend | CRUD `/api/v1/{teams,users,customers,products,leads,quotes,policies,claims,alerts,ai-calls,campaigns,…}` | Dominio |

## Estructura (monorepo polyglot)

```
apps/
  backend/            # NestJS 11 + Prisma — dominio multi-tenant + gateway WS live-call (:3001)
  ai/                 # Python FastAPI — chat SSE, voz en vivo (Deepgram), 33 tools, cotizador,
                      #   PDF, KYC Didit, firma, checklist, callback landing, email (:8085)
  frontend/           # React 19 + Vite + Tailwind v4 — landing + app por roles (nginx :8090)
  services/
    hermes-agent/     # workspace Hermes: SOUL.md, skills — canal WhatsApp
    baileys-bridge/   # gateway WhatsApp propio (perfil "baileys")
    deepgram-outbound/# referencia de telefonía saliente Deepgram+Twilio (perfil "voice-outbound")
data/market/          # aseguradoras LATAM + FX de reguladores + catálogo + requisitos
deploy/               # nginx (local y Railway), Dockerfiles, RAILWAY.md, DEPLOYMENT.md
docs/                 # PLAN, FUSION, AUDITORIA, RETO_COLSUBSIDIO, ROADMAP_MCKINSEY, DDL
openspec/             # specs y diseño de los cambios grandes (voice agent, live call)
docker-compose.yml    # stack completo + perfiles voz/hermes/baileys/voice-outbound
```

## Cumplimiento

Tequendama **cierra la venta de forma autónoma**: Colsubsidio actúa como distribuidor y
la aseguradora emite. Antes de emitir se exige y registra el **consentimiento de
habeas data** (Ley 1581/2012) y el consentimiento **biométrico** separado del KYC;
se verifica la identidad (Didit: documento + prueba de vida); se firma
electrónicamente (Ley 527/1999); se divulgan aseguradora, coberturas, exclusiones y
prima; se informa el **derecho de retracto** (Ley 1480/2011); y el takeover humano
está disponible en cualquier momento si el cliente lo pide.

---

<div align="center">
  <sub>Monorepo del equipo <b>Salto Ángel</b> — Hackathon Colsubsidio 30X · 2026</sub>
</div>
