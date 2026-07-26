# Roadmap IA — basado en "The future of AI in the insurance industry" (McKinsey)

> Plan de implementación de las 7 features derivadas del paper, con el diseño de
> integración exacto sobre la arquitectura actual (NestJS + Prisma / FastAPI IA /
> React Tequendama / Hermes WhatsApp). Julio 2026.

## Estado: ✅ IMPLEMENTADO (23 jul 2026)

Las 7 features están implementadas según este diseño, con estos ajustes:
- **Voz (F6)**: la fase A quedó con dictado por **Web Speech API** del navegador
  (sin dependencia `faster-whisper`) + TTS vía `GET /api/assistant/tts` (proxy a
  Kokoro). La fase B (hacer real `/llamada` con `AiCall`/`CallMessage`) sigue
  pendiente.
- **Underwriting (F2)**: el REFER crea la alerta en `AlertsPanel`; el botón
  "Aprobar y emitir" en el panel quedó como mejora futura (hoy el gerente
  aprueba emitiendo vía checkout/chat).
- **Paridad de modo demo**: se omitió a propósito — la demo corre con
  `DEEPSEEK_API_KEY` configurada.
- **Seeds**: la migración `20260723090000_claims` siembra una póliza que vence
  en 15 días (`POL-2026-DEMO01`) y un reclamo (`CLM-2026-DEMO01`) para que
  renovaciones, ClaimsPanel y `proponer_renovacion` sean demoables de inmediato.

## Qué ya cubre el sistema vs. el paper

| Tesis del paper | Estado en Tequendama |
|---|---|
| Distribución conversacional hiperpersonalizada | 🟢 Chat SSE + WhatsApp + perfilado (`profiling.py`) + memoria multi-tenant |
| Cierre autónomo (quote → bind) | 🟢 `emitir_poliza` → `POST /api/v1/checkout` + pago Polar + PDF de póliza |
| Underwriting semiautónomo con escalado humano | 🟡 el cierre emite siempre; **no hay decisión de riesgo ni escalado** → Feature 2 |
| Pricing por segmentación de riesgo | 🟡 factores edad/riesgo del catálogo; **no usa el perfil del cliente** → Feature 3 |
| Gestión de reclamos (claims) | 🔴 inexistente → Feature 1 |
| Seguro embebido en punto de compra | 🔴 inexistente → Feature 4 |
| Renovaciones y cross-sell proactivos | 🟡 `proactive.py` cubre funnel de venta; **no mira pólizas emitidas** → Feature 5 |
| Voice agents (entrante) | 🟡 TTS saliente (Kokoro) + STT en WhatsApp (Hermes); **la web no tiene voz** y `/llamada` es un demo guionado → Feature 6 |
| Medir el impacto (KPIs del paper) | 🟡 KPIs básicos en dashboard; faltan tiempo-de-cotización, % auto-emisión, conversión → Feature 7 |

## Priorización

| # | Feature | Valor demo | Esfuerzo | Fase |
|---|---|---|---|---|
| 7 | KPIs "McKinsey" en panel gerencial | Alto (pitch con números) | Bajo | F1 |
| 3 | Pricing personalizado por riesgo | Alto | Bajo | F1 |
| 5 | Renovaciones + cross-sell proactivo | Medio | Bajo | F1 |
| 2 | Underwriting semiautónomo (pipeline agéntico) | Muy alto | Medio | F2 |
| 1 | Reclamos (FNOL) por chat/WhatsApp | Muy alto | Medio-alto | F2 |
| 4 | Seguro embebido (quote & bind para aliados) | Alto (ángulo B2B2C) | Medio | F3 |
| 6 | Voz entrante en la web (`/llamada` real) | Alto (efecto wow) | Alto | F3 |

Regla transversal: **toda tool nueva se registra en `TOOLS_SCHEMA` + `_exec_tool`
(`apps/ai/app/agent_core.py`) y queda disponible en ambos canales** (chat síncrono
`/api/chat` y streaming `assistant.py`); el modo demo sin `DEEPSEEK_API_KEY`
(`_parse_intent` / `_run_demo` en `assistant.py`) necesita cableado paralelo para
que la demo funcione sin API key.

---

## Feature 1 — Reclamos (FNOL: primer aviso de siniestro)

Cierra el ciclo venta → póliza → **siniestro**, la mitad de la cadena de valor que hoy falta.

**Backend (`apps/backend`)**
- `schema.prisma`: modelo `Claim` (`claims`): `teamId?`, `policyId` FK, `customerId`,
  `claimNumber` único (`CLM-2026-000NNN`), `insuranceType`, `status` enum
  `ClaimStatus` (`REPORTADO → EN_REVISION → DOCS_PENDIENTES → APROBADO/RECHAZADO → PAGADO`),
  `incidentDate`, `description`, `amountEstimateCop?`, `fraudScore?` Decimal(3,2),
  `fraudFlags` JsonB, `documents` JsonB (file_ids de uploads), `aiSummary?`.
- Módulo `claims` calcado del patrón tenant-scoped (`OptionalJwtAuthGuard` +
  `@TenantId()`, como `policies`): CRUD + `PATCH /api/v1/claims/:id/status`.
- Migración + seed de 2-3 siniestros demo.

**Servicio IA (`apps/ai/app`)**
- Nuevo `claims_ai.py` con 3 tools: `reportar_siniestro` (valida nº de póliza contra
  `public.policies` vía la BD compartida, crea el claim vía `POST /api/v1/claims` con
  `X-Tenant-Id` — mismo patrón que `emitir_poliza`), `estado_siniestro`,
  `documentos_siniestro` (qué falta según tipo).
- Triage determinista (patrón `profiling.py`, nada de precios del LLM): severidad por
  monto/tipo, y `fraudScore` con heurísticas: siniestro < 30 días tras `startDate`,
  monto vs prima anual, reclamos repetidos del mismo documento. Flags → JsonB.
- Requisitos de documentos por tipo en `data/market/requisitos_siniestros.json`
  (mismo formato data-driven de `requisitos_seguros.json` que consume `intake.py`).
- El upload ya existe (`POST /api/assistant/upload` + `analizar_documento` en
  `files.py`): añadir extractores para denuncia/facturas (`_detect_tipo`).

**Frontend (`apps/frontend`)**
- SSE: 2 eventos nuevos en el contrato (documentarlos en `docs/FUSION.md`):
  `claim_step` (espejo de `checkout_step`) y `claim` (tarjeta con nº y estado).
- `useAssistantChat.ts`: añadir `claim` a `ChatMessage` y al `dispatch` (mismo patrón
  que `policy`). Nuevo `features/assistant/ClaimCard.tsx` (stepper + tarjeta, clonando
  la estructura de `PolicyCard.tsx`; paleta: ámbar en revisión, verde aprobado).
- Panel gerencial: `features/manager/ClaimsPanel.tsx` (tabla estado + banderas de
  fraude en rojo) + método `api.claims(teamId)` en `src/lib/api.ts`.

**WhatsApp**: skill `siniestros` en `apps/services/hermes-agent/skills/` (reporta,
adjunta fotos — Hermes ya recibe media —, consulta estado).

**Demo**: "Chocaron mi carro 😭" → pide póliza + fotos → triage → tarjeta
"Reclamo CLM-2026-000123 en revisión" → aparece en el panel del gerente con score de fraude.

---

## Feature 2 — Underwriting semiautónomo (pipeline agéntico con escalado)

El paper describe agentes de intake → riesgo → pricing → cumplimiento → orquestador.
Intake (`intake.py`), riesgo (`profiling.py`) y pricing (`quoting.py`) ya existen;
falta la **decisión** y el **escalado humano**.

**Servicio IA**
- Nuevo `underwriting.py`: `evaluate(profile, product, datos) → {decision, reasons[]}`
  con decision ∈ `AUTO_APPROVE | REFER | DECLINE`. Reglas deterministas y auditables:
  banderas de `profiling._banderas` (edad extrema, salud declarada, SARLAFT),
  prima mensual > umbral por tipo, suma asegurada > umbral, datos inconsistentes.
- Integración en el cierre: `emitir_poliza` (en `agent_core.py`) llama `evaluate`
  **antes** del checkout. `AUTO_APPROVE` → flujo actual sin cambios. `REFER` →
  crea `Alert` (severidad `alta`) vía `POST /api/v1/alerts`, deja el lead en
  `NEGOCIACION`, y responde al cliente "un asesor te confirma en menos de 24h".
  `DECLINE` → mensaje honesto + alternativas de otro producto.
- Auditoría: la decisión + razones se guardan en `Quote.coverage.underwriting`
  (JsonB ya existente, mismo truco que `coverage.payment`).

**Backend**
- Sin modelo nuevo: se reutilizan `alerts` (cola de referidos) y `checkout`.
  Añadir al `checkout.service.ts` la aceptación de `underwriting` dentro del body para
  persistirlo en `Quote.coverage`, y `agentId` cuando el cierre es aprobado por humano.

**Frontend**
- SSE: evento `underwriting` (`{decision, reasons}`) → en `AssistantChat` una tarjeta
  compacta: verde "Aprobada automáticamente" / ámbar "En revisión por un asesor".
- Panel gerencial: los REFER llegan solos a `AlertsPanel` (ya consume
  `api.alerts(teamId)`); añadir botón "Aprobar y emitir" que llame
  `POST /api/v1/checkout` con el payload guardado en la alerta.

**Demo**: cliente de 29 años, vida, prima baja → póliza emitida sola en el chat;
cliente de 67 con condición de salud → "escalado a asesor" y la solicitud aparece
en el dashboard del gerente para aprobar con un clic. Ese contraste ES la tesis del paper.

---

## Feature 3 — Pricing personalizado por segmentación de riesgo

**Servicio IA (solo Python, cero cambios de contrato)**
- `quoting.quote_product`: nuevo parámetro opcional `perfil` (salida de
  `build_profile`). `_segmento_riesgo` → multiplicador acotado (bajo 0.90, medio 1.00,
  alto máx 1.15) aplicado a la prima, **siempre con línea explicativa en el
  `breakdown`** (`{"concepto": "Ajuste por perfil (bajo riesgo)", "factor": 0.90}`).
  Determinista, con tope ±15%, nunca decidido por el LLM.
- Tool `cotizar` en `agent_core.py`: antes de cotizar, carga `intake_session` de la
  sesión y llama `build_profile`; pasa `perfil` al cotizador. El agente puede explicar
  el porqué del precio ("tu perfil de bajo riesgo te da 10% menos").
- `documents.build_quote_pdf`: el breakdown ya se renderiza en tabla — la línea de
  ajuste sale gratis en el PDF.

**Frontend**: nada obligatorio (viaja en el markdown del chat). Opcional: chip
"Precio personalizado ✓" en la tarjeta de cotización.

**Demo**: dos cotizaciones del mismo producto con perfiles distintos → primas
distintas y explicadas. Responde directamente al "la prima refleja tu riesgo real,
no un promedio" del paper.

---

## Feature 4 — Seguro embebido (quote & bind para aliados)

**Backend Nest** (dueño de Polar create checkout + webhook — secrets en Nest)
- Router `embedded.py` (servicio IA): `POST /api/embedded/quote` (`{partner_key, tipo, contexto}` →
  prima vía `quoting.quote_product`) y `POST /api/embedded/checkout` (Nest
  `POST /api/v1/payments/checkout` crea el link Polar; al aprobarse el webhook, el flujo
  existente emite la póliza vía `POST /api/v1/checkout`). Auth por `PARTNER_API_KEYS`
  en `config.py` (patrón `require_service`); rate-limit simple con Redis (ya está en
  el compose y sin uso intensivo).

**Frontend**
- Ruta pública `/embed` **fuera** de `RequireAuth` y sin `AppShellLayout` (en
  `App.tsx`): `pages/EmbedQuotePage.tsx` — mini-tarjeta autocontenida (tokens
  Tequendama, sin TopNav) con: tipo de seguro preseleccionado por query param,
  prima, botón "Protéger mi compra" → checkout Polar. Pensada para iframe.
- Sección "Para aliados" en la landing (`features/landing/`) con un iframe de
  ejemplo simulando el checkout de un e-commerce.

**Demo**: página falsa "TiendaViajes" con el widget embebido: el usuario compra un
tiquete y agrega seguro de viaje en 2 clics sin salir del flujo. Caso de
distribución estrella del paper (punto de compra).

---

## Feature 5 — Renovaciones y cross-sell en el motor proactivo

**Servicio IA**
- `proactive.py`: el servicio ya comparte Postgres con Prisma — leer
  `public.policies` (join `public.customers`) y añadir dos generadores de nudges:
  `renovacion_proxima` (`endDate` < 30 días → renovación pre-cotizada con
  `quoting.quote_product`) y `cross_sell` (tiene AUTO y no VIDA → sugerir según
  `profiling._productos_recomendados`).
- Tool nueva `proponer_renovacion(policy_number)` → cotiza la renovación y arranca
  el checkout existente.
- `reports.py`: incluir renovaciones próximas en el email del gerente (el HTML
  builder ya existe).

**WhatsApp**: la skill `seguimiento-proactivo` ya consume `GET /api/proactive` con
cron — los nudges nuevos salen solos por ese canal.

**Frontend**: `AlertsPanel` ya lista alertas del backend; los nudges de renovación
llegan por `/api/proactive` (manager). Opcional: saludo proactivo en el
`EmptyState` del chat si la sesión tiene póliza por vencer.

**Demo**: sembrar una póliza con `endDate` a 15 días → el gerente ve la alerta, el
cliente recibe el nudge y renueva en el chat.

---

## Feature 6 — Voz entrante (hacer real `/llamada`)

Hoy `/llamada` (`LiveAiCallPage.tsx`) es un guion animado. Los modelos `AiCall` +
`CallMessage` y el módulo `ai-calls` del backend **ya existen y están sin uso**: esta
feature los estrena.

**Servicio IA**
- `POST /api/assistant/transcribe`: STT local con `faster-whisper` (CPU, modelo
  `small` es suficiente en español; nueva dep en `requirements.txt`).
- `GET /api/assistant/tts?text=`: proxy al Kokoro del compose (perfil `voz`,
  `http://seguria-tts:8880/v1/audio/speech`, voz `ef_dora`) para no exponer el
  contenedor TTS al navegador.

**Frontend**
- Fase A (barata): botón de micrófono en el input de `AssistantChat` —
  `MediaRecorder` → `/api/assistant/transcribe` → `sendMessage(texto)`; toggle
  "responder con voz" que pasa la respuesta final por el endpoint TTS.
- Fase B: `LiveAiCallPage` real: loop grabar → transcribir → stream SSE → TTS →
  reproducir, reutilizando el orb visualizador que ya está en `index.css`. Cada
  llamada crea un `AiCall` y cada turno un `CallMessage` vía `/api/v1/ai-calls` —
  con lo que el KPI "Llamadas IA hoy" del dashboard pasa de mock a real.

**Demo**: conversación por voz de punta a punta en la web, con transcript guardado
y contando en el KPI del gerente.

---

## Feature 7 — KPIs "McKinsey" en el panel gerencial

Instrumentar las métricas con las que el paper argumenta el impacto.

**Backend**
- `dashboard.service.ts` (raw SQL, como los actuales): `tiempo medio de cotización`
  (lead `createdAt` → primer quote), `% de auto-emisión` (policies con
  `agentId IS NULL` / total), `conversión` (leads → policies), `tiempo de cierre`
  (lead `createdAt` → `closedAt`), y cuando exista Feature 1, `ciclo de reclamo`.
  Exponer en `GET /api/v1/dashboard/ai-impact`.

**Frontend**
- `features/manager/AiImpactCard.tsx`: fila de stat-tiles con `CountUp` (ya existe
  el componente) — "Cotización en 38s", "82% pólizas sin humano", "Conversión 24%".
  Se agrega al `Promise.all` de `ManagerDashboardPage` con fallback a mock, como
  los demás widgets.

**Servicio IA**
- `insights.summary()`: mismas métricas para que el gerente las pregunte por chat
  (`obtener_insights`) y salgan en el email de `reports.py`.

---

## Fases y orden de ejecución

**F1 — Quick wins (≈1 día)**: Feature 7 → 3 → 5. Sin modelos nuevos, sin cambios de
contrato SSE; máximo retorno para el pitch.

**F2 — Núcleo agéntico (≈2-3 días)**: Feature 2 (primero: reutiliza todo) y
Feature 1 (la única con migración Prisma). Al final de F2 el demo cubre la cadena
completa: descubrir → cotizar (precio personalizado) → underwriting → pagar →
póliza → renovar → siniestro, con escalado humano visible en el dashboard.

**F3 — Expansión (según tiempo)**: Feature 4 (embebido) y Feature 6 (fase A mic;
fase B `/llamada` real solo si sobra tiempo).

**Transversales (no negociables)**
1. Paridad del modo demo: cada tool nueva necesita su rama en `_parse_intent` /
   `_run_demo` de `assistant.py` para que la demo funcione sin `DEEPSEEK_API_KEY`.
2. Seeds: pólizas con vencimiento próximo, un siniestro y un referral en
   `_seed_demo` (IA) y el seed de Prisma, para que dashboard y nudges se vean vivos.
3. Contrato SSE: documentar los eventos nuevos (`claim_step`, `claim`,
   `underwriting`) en `docs/FUSION.md` — es el contrato que frontend e IA deben cumplir.
4. Tests: extender `tests/test_api.py` (patrón `_exec_tool` directo) para
   `evaluar_riesgo`, `reportar_siniestro` y el ajuste de pricing.
