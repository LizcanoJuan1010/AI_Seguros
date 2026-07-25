# Plan: corretaje real hacia aseguradoras + checklist asíncrono + marketing social

> Contexto para que otro agente (u otra sesión) continúe el trabajo de código.
> No es una feature lista para picotear una sola tarea — son 4-5 hilos de
> trabajo relacionados, con distinto nivel de definición. Cada sección dice
> qué existe hoy (no reconstruir), qué falta, y qué decisiones de negocio
> están pendientes antes de poder codificar con confianza.

## 1. Visión de negocio (el porqué)

Tequendama/SegurIA **no es la aseguradora — es el corredor/intermediario**,
exactamente como Colsubsidio en la vida real (https://www.colsubsidio.com/seguros):
recolecta al cliente, arma el expediente (datos, KYC, consentimiento, firma,
pago), y al cerrar la venta **entrega ese expediente a la aseguradora real**
que sí asume el riesgo y emite la póliza. Hoy el sistema simula ese cierre
completo dentro de su propia base de datos — el puente hacia la aseguradora
real todavía no existe (ver §3.4).

## 2. Estado actual (NO reconstruir esto — es la base sobre la que se apoya todo lo nuevo)

### 2.1 Tres agentes conversacionales, cada uno con su rol en el embudo
- **Sofía** (web, informativa/cross-sell) — `apps/ai/app/agent_core.py::SYSTEM_PROMPT_WEB`.
- **Camilo** (WhatsApp, cierra la venta) — `apps/ai/app/agent_core.py::SYSTEM_PROMPT_WHATSAPP`,
  con tools en `TOOLS_SCHEMA_WHATSAPP` (incluye `enviar_nota_voz`, Deepgram).
  Recibe audio real de WhatsApp (transcrito) — ver `whatsapp_inbound` en `main.py`.
- **Martín** (llamada saliente, cierre para leads CALIENTES) —
  `apps/ai/app/reference/elevenlabs_agent_prompt.md` (vive en el dashboard de
  ElevenLabs, este archivo es solo la fuente de verdad para pegarlo ahí).
  Se dispara con `apps/ai/app/calls.py::iniciar_llamada`.
- Los 3 prompts de Sofía/Camilo/Gerente están versionados en Supabase
  (`docket.versions`, motor en `apps/ai/app/docket_engine/`) — cambiarlos no
  requiere tocar código, ver `docs/` de esta sesión si hace falta el detalle.

### 2.2 Piezas del "checklist" — YA EXISTEN, pero sueltas (no unificadas)
- **KYC** — `apps/ai/app/kyc.py`: verificación de identidad vía Didit
  (Workflow/session real, no las APIs standalone). Magic-link `/kyc/{token}`.
- **Firma electrónica** — `apps/ai/app/esign.py`: clickwrap in-house,
  magic-link `/sign/{token}`.
- **Pago** — `apps/ai/app/payments.py`: checkout de Polar (sandbox).
- Hoy estos 3 pasos se disparan **secuencialmente dentro de la conversación**
  con Camilo (tools `generar_verificacion_identidad` → `evaluar_riesgo` →
  `generar_firma_poliza` → pago → `emitir_poliza`), cada uno mandando su
  propio link por WhatsApp/correo en el momento en que la charla llega ahí.
  **No existe una vista única** donde el cliente vea "te faltan estos 3
  pasos" y los complete cuando quiera, sin depender de seguir chateando.

### 2.3 Lead scoring y canales — ya modela "primer contacto", pero nadie lo alimenta desde redes
- `apps/backend/prisma/schema.prisma`: `Lead.firstChannel`/`highestChannel`
  usan el enum `Channel` (`WEB_INTEREST`, `WHATSAPP`, `EMAIL`, `WEB_CHAT`,
  `VOICE_CALL`). **`WEB_INTEREST` ya existe en el modelo** — pensado
  exactamente para "clic/interés previo a cualquier conversación real" (ver
  comentario en el schema) — pero hoy **nada crea un Lead con ese canal**.
- `apps/backend/src/modules/leads/lead-scoring.service.ts`: calcula
  `intent` (CALIENTE/TIBIO/FRIO) y `priorityScore` a partir de la
  progresión de canal + tiempos de respuesta. Ya soporta que un lead
  "empiece caliente" si su `firstChannel` es de alto valor.

### 2.4 Campañas de marketing con Gemini — construido, en PR sin mergear
- `apps/ai/app/marketing_studio.py` (banners con Gemini, paleta real de
  Colsubsidio) + `apps/backend/src/modules/campaigns/` (persistencia,
  envío segmentado por `Lead.intent`) — **todo esto vive en la rama
  `feat/campanas-marketing-gemini` (PR #8), sin mergear a `main` todavía**.
  Antes de construir §3.5 hay que decidir si se mergea ese PR primero.
- **No existe ninguna integración con Instagram/LinkedIn** (ni publicar, ni
  leer likes/comentarios) — eso es 100% nuevo, ver §3.5.

### 2.5 Catálogo de productos — hoy es data de demo, no la fuente real
- `apps/ai/app/quoting.py` + tabla `products` (schema `seguria`) + el
  bloque `CATÁLOGO` hardcodeado en `apps/ai/app/reference/elevenlabs_agent_prompt.md`:
  5 productos inventados para la demo (Vida Protege, Hogar Tranquilo, Auto y
  Moto, Salud Complementaria, Ingreso Seguro), con aseguradoras de ejemplo
  (Seguros Bolívar, Sura, Allianz, Colmédica). **No están sincronizados con
  lo que Colsubsidio realmente vende hoy en colsubsidio.com/seguros.**
  El MODELO de datos para esto ya se resolvió — ver "✅ Ya resuelto" en §3.1.

## 3. Trabajo nuevo

### 3.1 Catálogo real desde colsubsidio.com/seguros
**Objetivo**: que `products` (y el `CATÁLOGO` de los 3 prompts) refleje los
planes/paquetes reales que Colsubsidio ofrece, no data inventada.

**✅ Ya resuelto (25 jul)**: el modelo de datos que faltaba para esto —
`apps/backend/prisma/schema.prisma` ganó un modelo `Insurer` propio (nombre,
NIT, `tipoIntegracion`, `apiConfig` JSON) referenciado desde `Product` y
desde `Policy` (snapshot de qué aseguradora emitió esa póliza puntual), y
`InsuranceType` pasó de 3 a los 10 tipos reales del catálogo LATAM
(`vida|auto|salud|hogar|viaje|pyme|accidentes|exequial|mascotas|movilidad`).
Migración `20260725120000_insurers`, aplicada y verificada contra la
Supabase real, con las 14 aseguradoras del mapa canónico LATAM ya
sembradas (sin `tipoIntegracion` todavía — eso sigue pendiente, ver abajo).
También se corrigió `apps/ai/app/main.py::_INSURANCE_TYPE_TO_PRISMA`, que
antes descartaba en silencio 7 de los 10 tipos al sincronizar leads.

**Sigue pendiente**: la fuente real de datos (ver decisión abajo) y el
backfill — hoy `Product.insurerId`/`Policy.insurerId` existen pero están
vacíos para los productos ya sembrados; falta mapear cada producto del
catálogo a su fila real en `insurers`.

**Decisión pendiente (bloquea empezar)**: ¿de dónde sale la data real?
- ¿Scraping de colsubsidio.com/seguros? (revisar legalidad/robots.txt antes)
- ¿Colsubsidio entrega un feed/API/Excel con su portafolio vigente?
- ¿Se captura a mano una vez y se actualiza manual? (más simple, pero se
  desactualiza)

**Una vez resuelto lo anterior**: la forma de aterrizarlo en código ya
existe — es la misma tabla `products` que ya lee `quoting.py` y el mismo
patrón `CATÁLOGO` de los prompts. Es un job de sincronización + actualizar
los 3 prompts (o mejor: que dejen de tener el catálogo hardcodeado y lo
llamen vía tool `buscar_productos`, que ya existe, en vez de tenerlo
también escrito en prosa dentro del prompt de Martín).

### 3.2 Conectar "primer contacto" (publicación + interés) con el Lead
**Objetivo**: cuando alguien interactúa con una publicación (like/comentario
en una red social sobre, ej., "seguro de mascotas"), eso crea o actualiza un
`Lead` con `firstChannel=WEB_INTEREST` y una categoría de interés — para que
cuando Camilo/Martín le hablen por primera vez, ya sepan por qué.

**Gap concreto**: no hay ningún `EventType` que represente "interacción en
red social" (`apps/backend/prisma/schema.prisma::EventType` solo tiene
`LLAMADA_SALIENTE|WHATSAPP|EMAIL|REUNION|NOTA|CAMBIO_ESTADO|REASIGNACION`) ni
un campo para "categoría de interés" en `Lead` (lo más cercano es
`insuranceType`, pero ese es el tipo YA cotizado, no el interés inicial).

**Sugerido**: agregar `EventType.INTERES_SOCIAL` (o similar) + un campo
`Lead.interesInicial` (string libre o el mismo enum `InsuranceType`) que se
llene cuando llega el primer contacto vía red social, ANTES de que haya
conversación — depende de §3.5 para tener de dónde sacar ese evento.

### 3.3 Vista de "checklist" asíncrona (KYC + firma + pago, sin depender de la llamada)
**Objetivo del usuario, textual**: "la vista del checklist es para que la
persona pueda hacerlo en el tiempo que sea, y que la llamada sea más para
continuar con el 'push' a la persona que está caliente que ya llegó a esta
vista del checklist".

O sea: hoy KYC/firma/pago son 3 links SUELTOS que Camilo manda en momentos
distintos de la charla. Lo que se pide es una **página única** (web, con un
solo link/token) que muestre los 3 pasos como checklist, cada uno
completable de forma independiente y en cualquier orden/momento, y que
Martín (la llamada) la use como ancla: "veo que te falta el paso 2, ¿seguimos?"
en vez de re-explicar todo desde cero.

**Piezas a reusar tal cual** (no reinventar): `kyc.py`, `esign.py`,
`payments.py` ya generan sus magic-links y guardan estado en Postgres
(`kyc_verifications`, tabla de `esign`, `Payment`). Lo nuevo es:
1. Un token/sesión "checklist" que agrupe los 3 (una tabla nueva, ej.
   `checkout_checklist` con `customer_id`/`lead_id` + 3 FKs opcionales a los
   3 sub-procesos, o simplemente una vista que consulta los 3 por
   `session_key`/`customer_id` — más simple, sin tabla nueva).
2. Una página `/checklist/{token}` (mismo patrón que `/kyc/{token}`/`/sign/{token}`
   en `main.py`) que muestre los 3 estados y links para completar cada uno.
3. Que Martín (prompt de la llamada) sepa CONSULTAR ese estado antes de
   llamar — hoy no tiene ninguna tool, solo lee `dynamic_variables` fijas
   (ver "Lo que este agente no puede hacer todavía" en el `.md` de
   referencia). Necesitaría un endpoint tipo `GET /api/checklist/{customer_id}`
   y registrarlo como Tool/webhook en el dashboard de ElevenLabs.

### 3.4 Flujo real de envío a la aseguradora (el corazón del "puente")
**Objetivo**: que al completar el checklist + cerrar la venta, los datos de
la póliza (asegurado, coberturas, prima, documentos KYC) se manden de verdad
a la aseguradora que corresponde (Seguros Bolívar / Sura / Allianz /
Colmédica en el catálogo actual), no solo se guarden en la base propia.

**✅ Modelo de datos ya resuelto (25 jul)**: `Insurer`/`Product.insurerId`/
`Policy.insurerId` ya existen (ver §3.1) — el "hueco de esquema" que hacía
imposible siquiera preguntar "¿a qué aseguradora le mando esto?" ya no
existe. Lo que sigue pendiente es el FLUJO real de envío, no el modelo.

**Decisión pendiente (bloquea seguir, y es la más importante de todo el
documento)**: hoy `emitir_poliza()` (`agent_core.py::_exec_tool`) llama
`POST /api/v1/checkout` del backend NestJS, que crea
Customer→Lead→Quote→Policy **solo en la base propia** — no hay ninguna
llamada a ninguna aseguradora real. Antes de construir esto hace falta saber,
por cada aseguradora del catálogo (ya con fila propia en `insurers`, falta
llenar su `tipoIntegracion`):
- ¿Tienen API de emisión? ¿Documentación disponible?
- Si no, ¿el "envío" es un correo con un PDF a un buzón del ramo, un
  formulario en su portal, un SFTP nocturno? Cada aseguradora puede pedir
  algo distinto — esto probablemente no es un solo flujo genérico sino un
  adaptador por aseguradora.

**Sugerido una vez haya respuesta**: un módulo nuevo tipo
`apps/ai/app/aseguradoras/` con un adaptador por aseguradora (interfaz común:
`enviar_poliza(policy, customer, coverage) -> {ok, referencia_aseguradora}`),
llamado desde `emitir_poliza()` justo después de crear la `Policy` propia —
mismo criterio "modo demo si no hay credenciales" que el resto del stack.

### 3.5 (Fase futura, menos definida) Minería de leads desde engagement social
**Objetivo del usuario, textual**: publicar en IG/LinkedIn un banner (ya se
pueden generar con Gemini, ver `marketing_studio.py` en PR #8) sobre una
categoría puntual (ej. "seguro de mascotas"), y luego identificar/contactar
a quienes le dieron like — leads ya pre-segmentados por interés.

**Esto es lo menos definido de todo el documento** — decisiones pendientes:
- ¿Publicar programáticamente en IG/LinkedIn, o solo generar la imagen y que
  alguien la suba a mano? (las APIs oficiales de Meta/LinkedIn para publicar
  y leer engagement tienen aprobación de app + permisos de negocio, no es
  trivial ni inmediato).
- El usuario mencionó una herramienta/API ("dapta") para esto que no alcancé
  a identificar con certeza — **hay que preguntarle directamente a qué se
  refería** antes de diseñar esta parte.
- Contactar gente que dio like a un post con un mensaje directo (DM) tiene
  bordes de plataforma/ToS a revisar — no asumir que es tan simple como
  llamar una API y ya.

**Lo que SÍ se puede dejar listo desde ya, sin resolver lo anterior**: el
banner con metadata + campaña (`marketing_studio.py`, `Campaign` en PR #8)
ya guarda `channel` (`INSTAGRAM_POST`/`INSTAGRAM_STORY`/`LINKEDIN`) y
`insuranceType` — el enganche con "quién le dio like" se conecta ahí cuando
se resuelvan las decisiones de arriba, alimentando el mismo `EventType.INTERES_SOCIAL`
de §3.2.

## 4. Decisiones de arquitectura ya tomadas (respetar, no rediseñar)
- Prisma/Postgres (Supabase) es la única fuente de verdad del dominio
  (Customer/Lead/Quote/Policy/Campaign); `apps/ai` tiene su propio schema
  `seguria` para lo operativo (cotizador, catálogo, sesiones), y cruza a
  `public.*` solo de lectura cuando hace falta (ver `proactive.py`).
- Todo lo que depende de una API externa (Didit, Polar, ElevenLabs, Deepgram,
  Gemini) corre en "modo demo" limpio sin su credencial — cualquier
  integración nueva (aseguradoras, redes sociales) debe seguir el mismo
  criterio: nunca romper el flujo si falta configurar algo.
- Los 3 agentes son personas separadas a propósito (Sofía/Camilo/Martín) —
  no volver a fusionarlos en un solo prompt.

## 5. Preguntas abiertas que hay que resolver con el negocio antes de codificar
1. Fuente real del catálogo de Colsubsidio (§3.1).
2. Por aseguradora del catálogo actual: ¿API, portal, correo? (§3.4) — esto
   define si es un desarrollo de software o un proceso operativo con un
   humano de por medio todavía.
3. Qué es "dapta" / qué herramienta de redes sociales tenía en mente el
   usuario (§3.5) — preguntar directo antes de diseñar esa fase.
4. ¿Se mergea el PR #8 (`feat/campanas-marketing-gemini`) antes de tocar
   §3.5, dado que esa fase depende de lo que ya construyó ese PR?

## 6. Orden sugerido
1. §3.3 (checklist asíncrono) — es la que tiene menos decisiones de negocio
   pendientes, reusa piezas que ya existen, y el usuario la describió con
   más detalle concreto.
2. §3.2 (conectar primer contacto) — depende en parte de §3.5 para tener de
   dónde sacar el evento, pero el modelo de datos (`EventType` nuevo) se
   puede dejar listo antes.
3. §3.1 y §3.4 — el modelo de datos (`Insurer`, `InsuranceType` de 10
   valores) ya está listo y aplicado (25 jul); lo que falta es puramente de
   negocio (§5.1, §5.2) — en cuanto haya respuesta, se puede empezar directo
   sin más trabajo de esquema. Mientras tanto no rompe nada dejarlo como está.
4. §3.5 — la más ambigua; no empezar sin resolver §5.3 primero.

## 7. División de trabajo entre sesiones (a partir del 25 jul)
- El **"cerebro"** — `SYSTEM_PROMPT_WEB`/`SYSTEM_PROMPT_WHATSAPP`
  (`agent_core.py`), el texto del prompt de Martín
  (`reference/elevenlabs_agent_prompt.md`), el motor de versionado/QA de
  prompts (`docket_engine/`), y en general cualquier ajuste de redacción,
  tono o flujo conversacional de Sofía/Camilo/Martín — lo trabaja **otra
  sesión**. No tocar la prosa de esos prompts desde este track.
- **Todo lo demás** — esquema/migraciones Prisma, módulos NestJS, los
  "tools" de Python (`kyc.py`/`esign.py`/`payments.py`/`marketing_studio.py`
  y sus endpoints), el wiring de `_exec_tool`, el checklist de §3.3, el
  `insurerId` de §3.1/§3.4, `backend_client.py`, y cualquier bug de
  plumbing/nombres de variable entre servicios — se sigue trabajando en
  esta sesión/track.
- Ejemplo ya aplicado (25 jul): el fix `nombre`→`nombre_cliente` en
  `elevenlabs.service.ts` es de "tools" (nombre de variable en un webhook,
  no el contenido del prompt) — se hizo acá. Si el pedido es cambiar QUÉ
  dice el prompt o CÓMO conversa el agente, es de la otra sesión.
