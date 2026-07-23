import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';

/**
 * Marca un handler/controlador como restringido a ciertos roles.
 * Ej.: `@Roles('GERENTE', 'ADMIN')` para endpoints gerenciales.
 * Requiere que el `JwtAuthGuard` haya poblado `req.user` antes del `RolesGuard`.
 */
export const Roles = (...roles: string[]) => SetMetadata(ROLES_KEY, roles);
