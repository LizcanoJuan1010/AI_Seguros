# Autenticación (login) + tenencia desde el login — patrón Paloma

> Se adapta el login de Paloma (`features/auth.py` + `AuthContext.tsx`): JWT HS256
> access+refresh, `authenticate_user` con bcrypt. Diferencia clave: **el JWT lleva
> `teamId`** → el tenant (organización) sale del login y fluye a todo el sistema.

## Modelo
- **Usuarios de plataforma** (agentes/gerentes/admin del equipo Colsubsidio o bróker)
  hacen login. Viven en la tabla `User` de Postgres (Tequendama) con `teamId` y `role`.
- El **tenant = `User.teamId`**; viaja dentro del JWT. Reemplaza el header manual
  `X-Tenant-Id` (que queda solo como fallback para servicio-a-servicio).
- Los **clientes finales** (a quienes se les vende) NO hacen login: siguen siendo la
  partición `user_id` (phone / web session) dentro del tenant del agente.

## Autoridad de auth: backend NestJS
- Prisma: `passwordHash String? @map("password_hash")` en `User` (migración).
- `@nestjs/jwt` (HS256, secret `JWT_SECRET`) + `bcrypt`.
- Endpoints (bajo `/api/v1`):
  - `POST /auth/login` `{email, password}` → valida bcrypt contra `User` →
    `{access_token, refresh_token, user:{id,email,name,role,teamId}}`.
  - `POST /auth/refresh` `{refresh_token}` → `{access_token, user}`.
  - `GET /auth/me` (Bearer) → el usuario.
- **Claims del access token**: `{sub:userId, email, name, role, teamId, type:"access", iat, exp}`.
  refresh: `{sub, email, type:"refresh", iat, exp}`. TTL: access 8h (`JWT_ACCESS_MINUTES=480`),
  refresh 7d (`JWT_REFRESH_DAYS=7`).
- `JwtAuthGuard` valida el Bearer; `@TenantId()` prefiere `req.user.teamId` del JWT,
  y solo cae al header `X-Tenant-Id`/tenant demo si no hay token (compatibilidad).
- `@Roles('GERENTE','ADMIN')` opcional para endpoints gerenciales (dashboard).
- Semillas: usuarios demo con contraseña bcrypt —
  - `gerente@colsubsidio.demo` / `demo123` → team A (`1111...`), rol `GERENTE`.
  - `agente@colsubsidio.demo` / `demo123` → team A, rol `AGENTE`.
  - `gerente@tenantb.demo` / `demo123` → team B (`2222...`), rol `GERENTE`.

## Servicio IA (Python)
- Reutiliza el decode HS256 de Paloma (sin PyJWT): módulo `app/auth.py` con
  `decode_access_token(token)` verificando firma+exp+type con `JWT_SECRET`.
- El endpoint SSE y `/api/chat` leen `Authorization: Bearer <access>`:
  - `tenant_id = claims.teamId` (si hay token válido); si no, `X-Tenant-Id`/demo.
  - `role = "gerente"` si `claims.role in {GERENTE, ADMIN}` else `"cliente"`.
    (reemplaza el `manager_key`, que queda como fallback).
- **`JWT_SECRET` compartido** entre backend y ai (misma env var).

## Frontend (React) — adaptado de AuthContext.tsx
- `AuthContext` (login/logout/refresh/auto-refresh 2 min antes de expirar; persiste en
  localStorage). `useAuth()` expone `{user, status, signIn, signOut, accessToken}`.
- Página `/login`; rutas protegidas (redirige a `/login` si no autenticado).
- **Todas** las llamadas a la API envían `Authorization: Bearer <access>` (chat SSE,
  dominio). El tenant ya NO se manda como header fijo: sale del token. El `role` del
  usuario decide UI (gerente ve panel; agente ve el asistente de venta).

## Plumbing
- `JWT_SECRET` en compose para `backend` y `seguria-ai` (misma clave; default demo).
- nginx reenvía `Authorization` por defecto (no requiere cambios).

## Verificación (criterio de aceptación)
1. `POST /api/v1/auth/login` con las credenciales demo → token con `teamId` correcto.
2. Con el token de team A, `GET /api/v1/policies` y el chat solo ven datos de A;
   con el de team B, solo los de B. **El tenant salió del login, no de un header.**
3. Credenciales inválidas → 401. Token expirado/ausente en endpoint protegido → 401.
