# Auditoría y mejoras SOTA — iteración julio 2026

## Hallazgos del SOTA aplicados

| Lección SOTA | Fuente | Cómo quedó implementada |
|---|---|---|
| 50-60% de interacciones de Erica son **proactivas** | BofA newsroom / CX Dive | `app/proactive.py`: nudges por cliente (cotización sin respuesta, cierre pendiente, descubrimiento frío) + alertas de negocio; endpoints `/api/proactive[/{phone}]`; skill `seguimiento-proactivo` con cron y límites anti-spam; bienvenida proactiva en la SPA |
| **Fiabilidad sobre amplitud**: respuestas curadas, no generación libre | American Banker / CX Dive | El LLM jamás da precios: toda cifra sale de herramientas deterministas (`cotizar`, `obtener_insights`); red de seguridad anti-"documento fantasma" (patrón Paloma) en `agent_core.py` |
| **Conversación guiada** (search-bar + sugerencias) | American Banker | Protocolo `SUGERENCIAS:` en los system prompts → quick-reply chips en la SPA |
| **Escalada a humano como parte del diseño** | Banking Dive | Prompts: pre-venta + asesor licenciado para emisión; etapa `cerrado` = agendar llamada humana |
| **Payloads estructurados y validados** (back-office de seguros) | Retell/Perspective AI 2026 | Function calling con JSON Schema, validación de país/etapas, upsert canónico de leads |
| **Completar el flujo**, no abandonar al primer obstáculo | Perspective AI 2026 | Loop multi-ronda (5) con reintentos; fallbacks: chat sin API key → cotizador rápido; Metabase caído → insights locales; Voicebox caído → solo texto |

## Auditoría de lo construido

**Corregido en esta iteración**
- La capa web no tenía lógica agéntica (solo formulario) → `agent_core.py` + `/api/chat` + chat UI.
- No existía seguimiento post-cotización (donde se cierra la venta) → motor proactivo completo.
- `asesor-seguros` no tenía técnica de venta → SPIN + manejo de 5 objeciones típicas.
- Config sin carga de `.env` → python-dotenv (sin pisar variables exportadas).
- Resultados de herramientas no expuestos al canal → `documents[]` en la respuesta del chat.

**Deuda conocida (aceptada para el hackathon)**
- `@app.on_event("startup")` está deprecado en FastAPI (funciona; migrar a `lifespan`).
- Historial de chat sin poda ni resumen (30 mensajes por sesión; suficiente para demo).
- Sin streaming SSE del chat web (Hermes sí transcribe/responde en tiempo real en WhatsApp).
- Sin suite pytest formal; la verificación fue end-to-end por HTTP y directa a `_exec_tool`.
- Takeover humano: diseñado en prompts/skills; la cola de handoff con UI es trabajo futuro
  (el patrón de referencia está en `reference/` y en el monitor de Paloma).

## Segunda iteración: auditoría adversarial de código (11 hallazgos, todos corregidos)

Un agente revisor independiente auditó el código nuevo. Resultado y correcciones:

| # | Sev | Hallazgo | Corrección |
|---|-----|----------|------------|
| 1 | ALTA | XSS almacenado en panel gerente (nombre/país/etapa/teléfono de lead vía `innerHTML`) | Función `esc()` de escape HTML aplicada a todo dato de API en `innerHTML` (tabla leads, alertas, barras) |
| 2 | ALTA | Endpoints con PII sin auth (`/api/leads`, `/api/conversations`, `/api/proactive/{phone}`) | Nueva dependencia `require_service` (header `X-Service-Key`); 4 endpoints internos protegidos |
| 3 | MEDIA | Truncar historial deja `tool` huérfano → API 400 | `_load_history` recorta el prefijo hasta el primer `user` (nunca abre con tool huérfano) |
| 4 | MEDIA | Sin try/except ni timeout en el LLM y en herramientas | `try/except` global (devuelve `llm_error` limpio) + `timeout=30, max_retries=2` + try/except por herramienta |
| 5 | MEDIA | `KeyError` si el modelo omite `country`/`quote_id` requeridos | Validación con `.get` y mensaje de error para el modelo |
| 6 | MEDIA | SQLite sin WAL → `database is locked` en concurrencia | `PRAGMA journal_mode=WAL` + `busy_timeout=5000` + `timeout=10` |
| 7 | MEDIA | Viaje cobraba 1 día por omisión; KPIs mezclaban por-viaje con mensual | Default de 15 días (marcado `dias_asumidos`); KPI de prima excluye productos `prima_por_dia`; campo "días de viaje" en la SPA |
| 8 | BAJA | Red de seguridad podía devolver afirmación falsa de documento | Flag `doc_claim_pending`: si agota rondas sin generar, se reemplaza por oferta honesta |
| 9 | BAJA | `/api/roles/{phone}` filtraba quién es gerente | Protegido con `require_service` |
| 10 | BAJA | CORS `allow_origins=["*"]` | Configurable por `CORS_ORIGINS` (default: solo same-origin) |
| 11 | BAJA | Extrapolación de edad usaba factor máximo, no banda contigua | `_age_factor` elige la banda contigua (menor/mayor extremo según edad) |

Se añadió además suite pytest (`tests/test_api.py`, 13 casos) y migración de
`@app.on_event` deprecado a `lifespan`.

## Verificación ejecutada
- `POST /api/chat` sin API key → degradación limpia (`llm_no_configurado`).
- `_exec_tool`: cotizar (PE salud 255,92 PEN), generar_documento (PDF real), gating de rol
  (cliente denegado en insights, gerente OK), país inválido rechazado.
- `/api/proactive`: 8 nudges + 2 alertas sobre los datos demo.
- SPA sirviendo chat + panel con alertas proactivas.
