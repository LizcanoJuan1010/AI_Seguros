# Arquitectura y contrato — Tequendama

> Decisión (confirmada por el usuario): **arquitectura polyglot** + **slice vertical
> end-to-end demoable** como primer hito.

## Arquitectura

```
Frontend React (Tequendama, Vite/Tailwind4, paleta Mist/Forest)
   │  REST + SSE
   ├── apps/backend/   NestJS 11 + Prisma 7  :3000   → Postgres   (dominio: leads, quotes, policies, teams, dashboard)
   └── apps/ai/        Python FastAPI        :8085   → Postgres + Redis   (cerebro: DeepSeek, memoria, chat SSE, cotizador, PDF, voz)
Infra: docker-compose → postgres:5432, redis:6379, backend, ai, frontend
Hermes = consola/prototipo opcional (fuera del camino caliente)
```

Regla de límites: el **backend NestJS** es el sistema de registro del dominio (Prisma
posee el esquema de negocio). El **servicio IA Python** posee sus propias tablas
(`memory`, `conversations`, estado de chat) y expone el chat; en fases siguientes sus
cotizaciones se escriben en las tablas del dominio vía la API NestJS.

## Alcance del slice (Fase 1)
1. Infra: `docker-compose` con Postgres + Redis + backend NestJS + servicio IA + frontend.
2. Backend NestJS corriendo sobre Postgres (migración + seed), con Dockerfile.
3. Servicio IA Python: **memoria multi-tenant en Postgres** (patrón Paloma, partición por
   `user_id`) + **chat por streaming SSE**; conserva cotizador/catálogo/PDF/insights.
4. Frontend: ruta **`/asistente`** en el React de Tequendama con el chat estilo Paloma
   **repintado a Mist/Forest**, consumiendo el SSE.
5. Flujo demo: **descubrir → cotizar → PDF** end-to-end.

Fuera del slice (fases siguientes): auth JWT, multitenancy completo (teamId en todas las
entidades), chat-jobs resumibles con Redis Streams, WhatsApp webhook, voz en el chat,
motor proactivo en la UI, escribir cotizaciones en las tablas NestJS.

## Contrato SSE (el frontend y el servicio IA DEBEN cumplirlo)

**Endpoint**: `POST {AI_URL}/api/assistant/chat/stream`
Body JSON: `{ "session_id": string, "message": string, "phone"?: string, "manager_key"?: string }`
Respuesta: `Content-Type: text/event-stream` (el frontend la consume con `fetch` +
`ReadableStream`, parseando frames SSE `event:`/`data:`).

Eventos (cada uno `data:` es JSON en una línea):
| event | data | UI |
|---|---|---|
| `thinking` | `{"text": "Analizando..."}` | indicador "pensando" (3 puntos / spinner) |
| `token` | `{"text": "<delta>"}` | concatenar y re-render markdown (streaming) |
| `tool_start` | `{"tool": "cotizar", "args": {...}}` | chip de herramienta con spinner |
| `tool_result` | `{"tool": "cotizar", "summary": "3 opciones", "meta": {...}}` | chip check verde |
| `quick_replies` | `{"items": ["...", "..."]}` | chips de sugerencia bajo la respuesta |
| `document` | `{"download_url": "/api/documents/xxx.pdf", "title": "Cotización"}` | chip de descarga PDF |
| `done` | `{"session_id": "..."}` | fin de stream |
| `error` | `{"message": "..."}` | burbuja de error |

Eventos añadidos por el cierre autónomo y el roadmap McKinsey (jul 2026):
| event | data | UI |
|---|---|---|
| `checkout_step` | `{"step":"datos\|consentimiento\|pago\|emision","fields"?:[...]}` | stepper del cierre (`CheckoutStepper`) |
| `payment_link` | `{"reference","checkout_url","amount_cop","status","demo"}` | tarjeta de pago Polar (`PaymentCard`) |
| `policy` | `{"policyNumber","download_url","title"}` | tarjeta verde "ya quedaste asegurada" (`PolicyCard`) |
| `underwriting` | `{"decision":"AUTO_APPROVE\|REFER\|DECLINE","label","reasons":[...]}` | tarjeta de evaluación de riesgo (`UnderwritingCard`) |
| `claim` | `{"claimNumber","status","tipo","poliza","documentos_requeridos":[...],"title"}` | tarjeta del reclamo FNOL (`ClaimCard`) — las banderas de fraude NUNCA viajan al navegador |
| `form` | spec de `generar_formulario` | formulario de intake en el chat |
| `profile` | salida de `perfilar_cliente` | tarjeta de perfil |
| `intake_progress` | `{"tipo","porcentaje","siguientes":[...]}` | barra de completitud del intake |

Notas:
- `session_id` estable por conversación (localStorage en el front) = clave de partición de memoria.
- Si no hay `DEEPSEEK_API_KEY`, el servicio IA igual **debe** streamear una respuesta
  demo coherente (tokens + una cotización real vía la herramienta) para que el slice sea
  demoable sin clave.
- Endpoints existentes que se conservan: `/api/products`, `/api/quotes`,
  `/api/quotes/{id}/document`, `/api/documents/{file}`, `/api/insights/*` (gerente).

## Tokens de color para el chat (paleta Mist/Forest de Tequendama)

El chat NO usa el dark-azul de Paloma; usa los tokens de Tequendama (`@theme` en
`apps/frontend/src/index.css`). Repintado:

| Rol en el chat | Paloma (origen) | Tequendama (destino) |
|---|---|---|
| Fondo del chat | `#080E1A` | `bg-background` (`#f1fdf0`) / `bg-surface` |
| Superficie/tarjetas | `#0B1120`/`#0f1729` | `bg-surface-container-lowest` (blanco) + `soft-forest-shadow` |
| Borde | `#1e3054` | `border-outline-variant` (`#c1c9bd`) |
| Burbuja usuario | cyan `#06B6D4` | `bg-primary-container text-white rounded-tr-none` |
| Burbuja/tarjeta IA | teñido por agente | `bg-white border-outline-variant/30 rounded-tl-none` + avatar `bg-primary` icono `psychology` |
| Acento primario | cyan | `text-primary` / `bg-primary` (`#083911`) |
| Acento acción/CTA | — | `bg-amber-cta text-primary` (`#ffbf00`) |
| Éxito/tool done | emerald | `text-primary` / `bg-primary-fixed` |
| Typing cursor | cyan | `bg-primary` (barra 3×18px, `@keyframes` blink 0.8s) |
| Código (H3/blockquote dorado) | `#d4a843` | `amber-cta` |

Tipografía: **Manrope** (cuerpo, `text-body-md`), **Sora** (labels, `text-label-md`).
Iconos: Material Symbols vía `<Icon name="send|mic|psychology|person|auto_awesome" />`.
Reusar primitivos `Button` (variante `cta` ámbar / `primary` verde / `ghost`), `Card`,
`Chip`, `Icon`. Radios: burbujas `rounded-2xl`, input `rounded-full`/`rounded-md`.

## Features del chat a portar (de Paloma, repintadas)
Streaming token-a-token con batching `requestAnimationFrame`; markdown
(`react-markdown` + `remark-gfm` + `rehype-highlight`); cursor typing; indicador
"pensando" (3 puntos `animate-bounce` / spinner); tarjetas/burbujas usuario-vs-IA;
chips de tool-calls con spinner→check; quick replies (empty state + tras respuesta);
chip de descarga de documento; auto-scroll suave; input auto-grow (Enter envía,
Shift+Enter salto); markdown responsive. (Framer Motion NO se necesita.)
