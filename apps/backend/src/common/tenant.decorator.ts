import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import type { Request } from 'express';

/**
 * Tenant (organización / Team) por defecto cuando el header `X-Tenant-Id`
 * no viene o no es un UUID válido. Corresponde al Team demo sembrado en la
 * migración multitenant (`Team.id = 11111111-1111-1111-1111-111111111111`).
 */
export const DEMO_TENANT_ID = '11111111-1111-1111-1111-111111111111';

export const TENANT_HEADER = 'x-tenant-id';

// Acepta cualquier versión de UUID (los ids de tenant sembrados 1111.../2222...
// no son v4, así que no se restringe la versión).
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Resuelve el tenant de la request a partir del header `X-Tenant-Id`.
 * Si falta o es inválido, devuelve el tenant demo. El valor siempre se
 * propaga como argumento a los services (nunca se guarda en estado global).
 */
export function resolveTenantId(value: unknown): string {
  const raw = Array.isArray(value) ? value[0] : value;
  if (typeof raw === 'string' && UUID_RE.test(raw.trim())) {
    return raw.trim().toLowerCase();
  }
  return DEMO_TENANT_ID;
}

/**
 * Resuelve el tenant de la request.
 *
 * Prioridad:
 *  1. `req.user.teamId` — el tenant que sale del JWT (login). Cuando un
 *     `JwtAuthGuard` valida un Bearer, adjunta `req.user` con el `teamId` de
 *     los claims; ese es el tenant autoritativo.
 *  2. Header `X-Tenant-Id` — fallback de compatibilidad (servicio-a-servicio,
 *     p.ej. el AI llamando al checkout, y pruebas existentes sin token).
 *  3. Tenant demo — si no hay ninguno de los anteriores.
 */
export const TenantId = createParamDecorator(
  (_data: unknown, ctx: ExecutionContext): string => {
    const request = ctx
      .switchToHttp()
      .getRequest<Request & { user?: { teamId?: string | null } }>();
    const fromToken = request.user?.teamId;
    if (typeof fromToken === 'string' && UUID_RE.test(fromToken.trim())) {
      return fromToken.trim().toLowerCase();
    }
    return resolveTenantId(request.headers[TENANT_HEADER]);
  },
);
