# DDL — toda la data del sistema Tequendama Insurance AI

> **UNA sola base: PostgreSQL** (unificado — ya no hay SQLite). Dos esquemas:
> - **`public`** — dominio del negocio (NestJS/Prisma): 12 tablas, 3 vistas, 10 enums.
> - **`seguria`** — runtime del servicio IA (catálogo LATAM, cotizador, memoria,
>   conversaciones, sesiones de intake/checkout, KYC/identidad): 11 tablas.
>
> DDL completo real: [`schema_postgres.sql`](schema_postgres.sql).

Regenerar el DDL desde el contenedor:
```bash
docker compose exec postgres pg_dump -U seguria -d seguria --schema-only > docs/schema_postgres.sql
```

---

## 1) PostgreSQL — dominio del negocio (fuente de verdad)

### Enums
| Enum | Valores |
|---|---|
| `user_role` | agente · gerente · admin |
| `user_status` | activo · inactivo · vacaciones |
| `insurance_type` | vida · auto · salud |
| `lead_status` | nuevo · contactado · cotizado · negociacion · cerrado_ganado · cerrado_perdido |
| `lead_intent` | caliente · tibio · frio |
| `quote_status` | borrador · enviada · aceptada · rechazada · vencida |
| `policy_status` | vigente · cancelada · vencida · suspendida |
| `call_status` | en_curso · completada · abandonada · transferida_humano · fallida |
| `speaker_type` | ia · cliente |
| `event_type` | llamada_saliente · whatsapp · email · reunion · nota · cambio_estado · reasignacion |

### Tablas y relaciones
Flujo de negocio: `Customer → AiCall → Lead → Quote → Policy`, agrupados por `Team` (tenant).

| Tabla | Propósito | Columnas clave | Tenant (`team_id`) |
|---|---|---|---|
| **teams** | Organización / tenant | id, name, manager_id→users | — (ES el tenant) |
| **users** | Agentes/gerentes/admin (login) | id, **team_id**, full_name, email (unique), **password_hash**, role, status | sí |
| **customers** | Cliente final | id, full_name, email, phone, document_type+**document_id** (unique), birth_date, city, **consent_data/consent_at**, **team_id** | sí |
| **products** | Productos de seguros | id, insurance_type, name, base_premium_cop, coverage_schema (jsonb), is_active | catálogo global |
| **ai_calls** | Llamada del agente IA | id, customer_id→customers, status, started/ended_at, **duration_sec** (generada), summary, intent, intent_score (0..1), sentiment, metadata (jsonb) | — |
| **call_messages** | Transcripción de la llamada | id, call_id→ai_calls, speaker (ia/cliente), content, spoken_at | — |
| **leads** | Oportunidad de venta (funnel) | id, customer_id→customers, ai_call_id→ai_calls (unique), agent_id→users, insurance_type, status, intent, closed_at, ai_next_steps (jsonb), **team_id** | sí |
| **lead_events** | Bitácora del lead | id, lead_id→leads, agent_id→users, event_type, notes, payload (jsonb) | — |
| **quotes** | Cotización | id, lead_id→leads, product_id→products, coverage (jsonb), monthly_premium_cop, status, valid_until, **team_id** | sí |
| **policies** | Póliza emitida | id, quote_id→quotes (unique), customer_id→customers, agent_id→users, **policy_number** (unique), status, start/end_date (CHECK end>start), monthly_premium_cop, **team_id** | sí |
| **alerts** | Alertas gerenciales | id, **team_id**, lead_id, agent_id, message, severity, resolved | sí |
| **memory** | Memoria del asistente (patrón Paloma) | id, **tenant_id**, **user_id**, content, category, hash, score · UNIQUE(tenant_id,user_id,hash) | sí (2 ejes) |
| **_prisma_migrations** | Control de migraciones Prisma | — | — |

**Multitenancy (dos ejes):** `team_id` (organización) en users/customers/leads/quotes/policies/alerts; `memory` particionada por `(tenant_id, user_id)`. El `tenant` sale del **login** (JWT lleva `teamId`).
*Aún sin `team_id` (global): ai_calls, call_messages, lead_events, products.*

### Vistas (dashboard gerencial)
- **v_daily_kpis** — llamadas_ia_hoy, duracion_promedio_sec, polizas_hoy, revenue_hoy_cop.
- **v_agent_performance** — rendimiento por agente.
- **v_hot_leads_uncontacted** — leads calientes sin contactar.

---

## 2) Esquema `seguria` (mismo Postgres) — runtime del servicio IA

Estado propio del cerebro (`apps/ai`, esquema `seguria` del mismo Postgres, vía
`psycopg`/`asyncpg`). No es el dominio: es el catálogo LATAM demo, el cotizador y el
estado conversacional. Aislado del `public` de Prisma para no chocar.

| Tabla | Propósito | Columnas clave |
|---|---|---|
| **products** | Catálogo LATAM (12 productos, JSON) | id, tipo, nombre, aseguradora, paises (json), suma_base_usd, prima_base_usd, prima_por_dia, coberturas (json), factores (json) |
| **fx_rates** | Tasas de cambio a USD | currency, date, usd_rate · PK(currency,date) |
| **leads** | Leads del asistente (demo/web) | id, phone (unique), name, country, age, stage, source |
| **quotes** | Cotizaciones del asistente | id, lead_id→leads, product_id→products, country, currency, sum_assured_usd, premium_monthly_usd/local, breakdown (json), status |
| **conversations** | Registro de mensajes | id, phone, role (cliente/asistente/gerente), channel, message, created_at |
| **chat_history** | Historial del chat por sesión | session_id, seq, message · PK(session_id,seq) · clave = `{tenant_id}:{session}` |
| **checkout_session** | Datos de cierre por sesión | session_key (`{tenant}:{user}`), full_name, document_id, birth_date, email, consent, consent_at |
| **intake_session** | Datos ricos del intake (JSON) | session_key (`{tenant}:{user}`), datos (json: ocupacion, ingresos, fumador, placa, preexistencias…) |
| **kyc_document** | Documentos KYC del cierre (cédula, autorización firmada, selfie, tarjeta de propiedad) | id, session_key, phone, tipo, file_id, path, status (recibido/verificado/rechazado), extracted (json) · UNIQUE(session_key,tipo) |
| **identity_verification** | Veredicto biométrico cédula↔selfie (YuNet + SFace, `app/identity.py`) | id, session_key, decision (aprobado/rechazado/revision/no_disponible), score, threshold, method, detail (json) |

**Nota:** el catálogo real de requisitos de intake (KYC/SARLAFT/underwriting por producto)
vive en [`../data/market/requisitos_seguros.json`](../data/market/requisitos_seguros.json)
(data-driven, no en tabla). El módulo `intake_session` guarda lo recolectado.

---

## Convención de tenencia (resumen)
- **Postgres dominio** → aislado por `team_id` (del JWT del login).
- **Postgres memory** → aislado por `(tenant_id, user_id)`.
- **SQLite sesiones** → `session_key = "{tenant_id}:{user_id}"` (user = phone o `web:{session}`).
