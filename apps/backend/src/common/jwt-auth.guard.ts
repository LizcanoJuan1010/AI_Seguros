import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import type { Request } from 'express';

/**
 * Usuario autenticado que se adjunta a `req.user` cuando llega un Bearer válido.
 * `teamId` es el tenant que el `@TenantId()` decorator prefiere sobre el header.
 */
export interface AuthUser {
  userId: string;
  email: string;
  role: string;
  teamId: string | null;
}

interface AccessTokenClaims {
  sub: string;
  email: string;
  role?: string;
  teamId?: string | null;
  type?: string;
}

function extractBearer(request: Request): string | null {
  const header = request.headers.authorization;
  if (!header || Array.isArray(header)) return null;
  const [scheme, token] = header.split(' ');
  if (scheme?.toLowerCase() !== 'bearer' || !token) return null;
  return token.trim();
}

async function verifyAndAttach(
  jwt: JwtService,
  request: Request,
  token: string,
): Promise<void> {
  let claims: AccessTokenClaims;
  try {
    claims = await jwt.verifyAsync<AccessTokenClaims>(token);
  } catch {
    throw new UnauthorizedException('Token inválido o expirado');
  }
  if (claims.type !== 'access') {
    throw new UnauthorizedException('Tipo de token inválido');
  }
  (request as Request & { user?: AuthUser }).user = {
    userId: claims.sub,
    email: claims.email,
    role: claims.role ?? '',
    teamId: claims.teamId ?? null,
  };
}

/**
 * Guard ESTRICTO: exige `Authorization: Bearer <access>` válido.
 * Ausente/ inválido → 401. Usado en endpoints protegidos (p.ej. GET /auth/me).
 */
@Injectable()
export class JwtAuthGuard implements CanActivate {
  constructor(private readonly jwt: JwtService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<Request>();
    const token = extractBearer(request);
    if (!token) {
      throw new UnauthorizedException('Falta el token de autenticación');
    }
    await verifyAndAttach(this.jwt, request, token);
    return true;
  }
}

/**
 * Guard OPCIONAL: si viene un Bearer lo valida y setea `req.user` (el tenant
 * saldrá del token); si NO viene ningún token, deja pasar y el tenant cae al
 * header `X-Tenant-Id`/demo (compatibilidad con el AI service-a-servicio del
 * checkout y con las pruebas existentes que usan header). Un token PRESENTE
 * pero inválido/expirado sí produce 401 (error explícito del cliente).
 */
@Injectable()
export class OptionalJwtAuthGuard implements CanActivate {
  constructor(private readonly jwt: JwtService) {}

  async canActivate(context: ExecutionContext): Promise<boolean> {
    const request = context.switchToHttp().getRequest<Request>();
    const token = extractBearer(request);
    if (!token) {
      // Sin token: se permite el acceso; el tenant se resuelve por header.
      return true;
    }
    await verifyAndAttach(this.jwt, request, token);
    return true;
  }
}
