# Multitenancy — patrón Paloma, de dos ejes

> Objetivo: aislamiento fuerte de datos, como los agentes de Paloma (partición dura,
> propagada por toda la cadena, nunca guardada en el singleton del orquestador).

## Dos ejes de tenencia
- **`tenant_id`** = la **organización** (equipo Colsubsidio / bróker). En el dominio
  Tequendama corresponde a `Team.id`. Aísla leads, quotes, policies, customers,
  y toda la memoria/estado del asistente entre organizaciones.
- **`user_id`** = el **cliente final** (teléfono de WhatsApp o `web:{session_id}`).
  Es la partición estilo Paloma para memoria/conversación/intake de cada persona.

**Clave de partición del asistente = `(tenant_id, user_id)`.** Nunca se cruzan datos
entre tenants ni entre usuarios.

## Contrato de propagación
- Header HTTP **`X-Tenant-Id`** en todas las llamadas (frontend → nginx → backend y ai).
  nginx lo pasa tal cual (tiene guiones, no se descarta). Si falta → tenant demo.
- **Tenant demo** (sembrado): `Team.id = 11111111-1111-1111-1111-111111111111`.
- El servicio IA lee `X-Tenant-Id`, particiona su estado por `(tenant_id, user_id)`, y
  al emitir póliza reenvía `X-Tenant-Id` al backend para crear la cadena en ese tenant.
- El backend resuelve `X-Tenant-Id` → `teamId`; si no viene, usa el tenant demo.

## Cambios en el dominio (NestJS)
1. Prisma: añadir `teamId String? @db.Uuid @map("team_id")` + relación a `Team` en
   **Customer, Lead, Quote, Policy** (migración). Sembrar el Team demo.
2. Resolución de tenant: decorador `@TenantId()` (o middleware) que lee `x-tenant-id`
   (default = Team demo). 
3. Alcance: todos los `findMany/findOne/create` de customers, leads, quotes, policies,
   checkout y las vistas del dashboard se filtran/asignan por `teamId`.
4. `POST /api/v1/checkout` crea Customer→Lead→Quote→Policy bajo el `teamId` resuelto.

## Cambios en el asistente (AI, Python) — patrón Paloma
1. **memory.py**: partición `(tenant_id, user_id)` — `UNIQUE(tenant_id, user_id, hash)`,
   todas las consultas `WHERE tenant_id=$1 AND user_id=$2`. Full-text search igual, con
   ambos filtros duros.
2. **Sesiones** (checkout_session, intake_session): `session_key = f"{tenant_id}:{user_id}"`.
3. **conversations / chat_history**: incluir `tenant_id` en la clave/fila.
4. **Propagación**: `/api/chat` y `/api/assistant/chat/stream` leen `X-Tenant-Id`
   (default `11111111-...-demo`) → `run_agent(tenant_id, user_id, ...)` →
   `_exec_tool(..., tenant_id=...)` → memoria y herramientas. El orquestador es
   singleton: `tenant_id`/`user_id` SIEMPRE van como argumentos, nunca en `self`.
5. `emitir_poliza` reenvía `X-Tenant-Id` al `POST /api/v1/checkout`.
6. Los 13 tests siguen verdes (default de tenant demo para no romperlos).

## Concurrencia (patrón Paloma, para WhatsApp/escala)
- Lock + rate-limit por `(tenant_id, user_id)` (o por `phone`). En un solo proceso:
  `asyncio.Lock` por clave con LRU acotado. Para escalar horizontalmente: Redis
  (`SET NX PX` como lock, `INCR`+`EXPIRE` para rate-limit).

## Seguridad (lección de Paloma)
- Endpoints que devuelven datos por id (póliza, job, lead) verifican que el `tenant_id`
  del solicitante coincide — no basta con un id adivinable.

## Verificación de aislamiento (criterio de aceptación)
- Dos tenants A (`1111...`) y B (`2222...`): una póliza/lead/memoria creada en A **no**
  es visible ni recuperable desde B, con el mismo `user_id`.
