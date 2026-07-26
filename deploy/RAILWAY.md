# Deploy a Railway (camino web: backend + ai + frontend)

Alcance de esta guía: chat web + panel gerencial. **Fuera de alcance**
(quedan igual solo en `docker-compose.yml` para local): WhatsApp
(hermes-agent, baileys-bridge), Kokoro TTS local, y el agente de voz
saliente (deepgram-outbound). Se pueden sumar después con el mismo patrón.

## Por qué esto y no `docker compose up` directo

Railway **no corre `docker-compose.yml`** cuando los servicios usan
`build:` (los tuyos todos lo usan) — cada servicio del compose se convierte
en un servicio de Railway aparte, con su propio Dockerfile. Verificado
contra la doc de Railway (jul 2026).

El frontend depende 100% de rutas relativas (`/api/v1/...`, `/api/...`)
asumiendo que backend/ai están detrás del MISMO origen (nginx local hoy) —
tocar eso para usar URLs absolutas rompería el login (hay un comentario
explícito en `AuthContext.tsx` advirtiéndolo). Por eso el frontend en
Railway sigue llevando nginx delante, con un `.template` nuevo
(`deploy/nginx.railway.conf.template`) que resuelve dos problemas que NO
existían en docker-compose:
1. Railway asigna `$PORT` dinámico — el template usa `listen ${PORT}`.
2. Las IPs internas de Railway **cambian en cada redeploy** de
   backend/ai; nginx cachea DNS al arrancar y sin el `resolver` +
   variable en `proxy_pass` del template, empieza a devolver 502 apenas el
   otro servicio se redespliega (Railway mismo recomienda Caddy por esto;
   el template usa el workaround documentado para seguir con nginx).

## 1. Postgres y Redis (managed, no los del compose)

En el proyecto de Railway: **+ New → Database → PostgreSQL** y
**+ New → Database → Redis**. Railway te da variables de referencia
(`${{Postgres.DATABASE_URL}}`, `${{Redis.REDIS_URL}}`) para usar en los
otros servicios sin copiar el string a mano.

Nota: el Postgres de Railway **no tiene pooler** (a diferencia de Supabase,
que sí distingue `DATABASE_URL` pooled de `DIRECT_URL` directa). Acá las
dos apuntan a la MISMA connection string — `prisma migrate deploy` (usa
`DIRECT_URL`) y el runtime (usa `DATABASE_URL`) funcionan igual.

Falta la extensión `vector` que usa el esquema `docket` (motor de
versionado de prompts, `DOCKET_ENGINE_ENABLED=false` por defecto — si lo
dejás en `false` no hace falta tocar nada acá).

## 2. Servicio `backend` (NestJS)

- **Root Directory**: `apps/backend`
- **Dockerfile**: detectado solo (`apps/backend/railway.json` ya apunta a `Dockerfile`)
- **Variables**:
  ```
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  DIRECT_URL=${{Postgres.DATABASE_URL}}
  JWT_SECRET=<generar uno real, no el demo>
  JWT_ACCESS_MINUTES=480
  JWT_REFRESH_DAYS=7
  SERVICE_API_KEY=<generar uno real>
  AI_SERVICE_URL=http://ai.railway.internal:8085
  CORS_ORIGINS=https://<dominio-publico-del-frontend>
  # Opcionales (dejar vacío = modo demo): POLAR_*, ELEVENLABS_*
  ```
- **Réplicas: dejá el backend en 1.** El tope de llamadas de voz anónimas
  simultáneas (`live-call.gateway.ts`, `MAX_ANON_POR_DISPOSITIVO`/
  `MAX_ANON_TOTAL`) es un Map en memoria por proceso: con N réplicas el tope
  real pasa a ser N veces el configurado y un mismo device_id puede abrir N
  llamadas a la vez, cada una facturando Deepgram. Mover eso a Redis es
  requisito previo para escalar horizontalmente.
  `PORT`: NO lo definas vos — Railway lo inyecta solo y `main.ts` ya lo
  respeta (`process.env.PORT ?? 3001`). Para que `AI_SERVICE_URL` de
  arriba sea estable, fijá manualmente el `PORT` del servicio `ai` (ver
  abajo) — si no, el puerto interno de `ai` puede cambiar entre deploys.

## 3. Servicio `ai` (FastAPI)

- **Root Directory**: `apps/ai`
- **Dockerfile**: detectado solo (`apps/ai/railway.json`)
- **Variables** (mínimas para que arranque; el resto ya degrada a modo demo):
  ```
  PORT=8085
  DATABASE_URL=${{Postgres.DATABASE_URL}}
  REDIS_URL=${{Redis.REDIS_URL}}
  BACKEND_URL=http://backend.railway.internal:3000
  JWT_SECRET=<el MISMO valor que en backend>
  SERVICE_API_KEY=<el MISMO valor que en backend>
  MANAGER_API_KEY=<generar uno real>
  CORS_ORIGINS=https://<dominio-publico-del-frontend>
  DEEPSEEK_API_KEY=<tu key real>
  DEEPSEEK_MODEL=deepseek-v4-flash
  # La llamada en vivo del navegador (/llamada) exige AMBAS keys — Deepgram
  # Y DeepSeek — o responde "Voice Agent no configurado" (no tiene modo demo).
  DEEPGRAM_API_KEY=<tu key real>
  DEEPGRAM_VOICE_MODEL=aura-2-celeste-es
  PUBLIC_BASE_URL=https://<dominio-publico-de-este-servicio-ai>
  ```
  Fijá `PORT=8085` a mano (no lo dejes que Railway lo asigne solo) — el
  `backend` de arriba apunta a `ai.railway.internal:8085`, y si Railway le
  asigna otro puerto dinámico ese link se rompe. Mismo motivo para fijar el
  `PORT` de `backend` (3000) si querés apuntar a él desde otro lado.

## 4. Servicio `frontend` (nginx + SPA)

- **Root Directory**: `.` (raíz del repo — el Dockerfile necesita copiar
  tanto `apps/frontend/` como `deploy/`, Docker no deja `COPY` fuera del
  contexto)
- **Dockerfile**: autodetectado (`railway.json` en la raíz del repo ya
  apunta a `deploy/frontend.railway.Dockerfile` — cada servicio solo lee el
  `railway.json` de SU PROPIO Root Directory, no hay conflicto con
  `apps/backend/railway.json` ni `apps/ai/railway.json`)
- **Puerto**: fijá `PORT=8080` como variable del servicio (ver sección de
  Variables abajo) — evita depender del puerto dinámico que Railway
  asignaría solo, necesario para poder generar el dominio público sin
  ambigüedad.
- **Variables**:
  ```
  PORT=8080
  BACKEND_INTERNAL_URL=http://backend.railway.internal:3000
  AI_INTERNAL_URL=http://ai.railway.internal:8085
  ```
  `PORT` lo inyecta Railway solo; el template ya lo usa (`listen ${PORT}`).

## 5. Orden de deploy

1. Postgres + Redis primero (Railway los deja listos casi al toque).
2. `backend` — corre `prisma migrate deploy` en el entrypoint; si Postgres
   no está aceptando conexiones todavía, este paso puede fallar en el
   primer intento (a diferencia de docker-compose, Railway no tiene un
   `depends_on: condition: service_healthy` automático entre servicios) —
   si falla, esperá unos segundos y reintentá el deploy desde el dashboard.
3. `ai` — depende de que `backend` ya tenga el dominio de negocio migrado.
4. `frontend` — depende de que `backend`/`ai` ya existan como servicios
   (para que `*.railway.internal` resuelva), no de que hayan terminado de
   arrancar del todo.

## 6. Verificación

- `https://<dominio-ai>/api/health` → `{"status":"ok","service":"seguria-api"}`
- `https://<dominio-frontend>/` → carga la SPA
- Login real desde el frontend (ejercita `/api/v1/auth/login` vía el proxy)
- Chat del asistente (ejercita SSE vía `/api/` → `ai`)

## Fuera de alcance de esta guía

`hermes-agent`, `baileys-bridge`, `deepgram-outbound`, `seguria-tts`
(Kokoro) — siguen solo en `docker-compose.yml`. Se agregarían con el mismo
patrón (Root Directory + Dockerfile por servicio) si hace falta.
