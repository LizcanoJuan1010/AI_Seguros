import {
  CanActivate,
  ExecutionContext,
  ForbiddenException,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import type { Request } from 'express';
import { AuthUser } from './jwt-auth.guard';
import { ROLES_KEY } from './roles.decorator';

/**
 * Valida `@Roles(...)`. Debe correr DESPUÉS del `JwtAuthGuard` (que puebla
 * `req.user`). Si el handler no declara roles, deja pasar. El rol se compara
 * en mayúsculas contra los nombres del enum Prisma (AGENTE/GERENTE/ADMIN).
 */
@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const required = this.reflector.getAllAndOverride<string[] | undefined>(
      ROLES_KEY,
      [context.getHandler(), context.getClass()],
    );
    if (!required || required.length === 0) {
      return true;
    }
    const request = context.switchToHttp().getRequest<Request & { user?: AuthUser }>();
    const user = request.user;
    if (!user) {
      throw new UnauthorizedException('Autenticación requerida');
    }
    const allowed = required.map((r) => r.toUpperCase());
    if (!allowed.includes((user.role ?? '').toUpperCase())) {
      throw new ForbiddenException('No autorizado para este recurso');
    }
    return true;
  }
}
