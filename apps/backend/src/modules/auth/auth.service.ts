import {
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import { PrismaService } from '../../prisma/prisma.service';
import { LoginDto, RefreshDto } from './auth.dto';

/**
 * Usuario "público" que se devuelve al cliente y se embebe (parte) en el JWT.
 * `teamId` es el tenant que sale del login y viaja dentro del access token.
 */
export interface PublicUser {
  id: string;
  email: string;
  name: string;
  role: string;
  teamId: string | null;
}

interface AccessClaims {
  sub: string;
  email: string;
  name: string;
  role: string;
  teamId: string | null;
  type: 'access';
}

interface RefreshClaims {
  sub: string;
  email: string;
  type: 'refresh';
}

@Injectable()
export class AuthService {
  // TTL en segundos (JwtSignOptions.expiresIn acepta number = segundos).
  private readonly accessTtlSec =
    Number(process.env.JWT_ACCESS_MINUTES ?? 480) * 60;
  private readonly refreshTtlSec =
    Number(process.env.JWT_REFRESH_DAYS ?? 7) * 86400;

  constructor(
    private readonly prisma: PrismaService,
    private readonly jwt: JwtService,
  ) {}

  /** Valida email + password (bcrypt) contra users.password_hash. */
  async validateUser(email: string, password: string): Promise<PublicUser> {
    const user = await this.prisma.user.findUnique({
      where: { email: email.trim().toLowerCase() },
    });
    if (!user || !user.passwordHash) {
      throw new UnauthorizedException('Credenciales inválidas');
    }
    const ok = await bcrypt.compare(password, user.passwordHash);
    if (!ok) {
      throw new UnauthorizedException('Credenciales inválidas');
    }
    return this.toPublicUser(user);
  }

  async login(dto: LoginDto) {
    const user = await this.validateUser(dto.email, dto.password);
    const [access_token, refresh_token] = await Promise.all([
      this.signAccess(user),
      this.signRefresh(user),
    ]);
    return { access_token, refresh_token, user };
  }

  async refresh(dto: RefreshDto) {
    let claims: RefreshClaims;
    try {
      claims = await this.jwt.verifyAsync<RefreshClaims>(dto.refresh_token);
    } catch {
      throw new UnauthorizedException('Refresh token inválido o expirado');
    }
    if (claims.type !== 'refresh') {
      throw new UnauthorizedException('Tipo de token inválido');
    }
    const record = await this.prisma.user.findUnique({
      where: { id: claims.sub },
    });
    if (!record) {
      throw new UnauthorizedException('Usuario no encontrado');
    }
    const user = this.toPublicUser(record);
    const access_token = await this.signAccess(user);
    return { access_token, user };
  }

  /** Devuelve el usuario del token (endpoint GET /auth/me). */
  async me(userId: string): Promise<PublicUser> {
    const record = await this.prisma.user.findUnique({
      where: { id: userId },
    });
    if (!record) {
      throw new UnauthorizedException('Usuario no encontrado');
    }
    return this.toPublicUser(record);
  }

  private signAccess(user: PublicUser): Promise<string> {
    const payload: AccessClaims = {
      sub: user.id,
      email: user.email,
      name: user.name,
      role: user.role,
      teamId: user.teamId,
      type: 'access',
    };
    return this.jwt.signAsync(payload, { expiresIn: this.accessTtlSec });
  }

  private signRefresh(user: PublicUser): Promise<string> {
    const payload: RefreshClaims = {
      sub: user.id,
      email: user.email,
      type: 'refresh',
    };
    return this.jwt.signAsync(payload, { expiresIn: this.refreshTtlSec });
  }

  private toPublicUser(user: {
    id: string;
    email: string;
    fullName: string;
    role: string;
    teamId: string | null;
  }): PublicUser {
    return {
      id: user.id,
      email: user.email,
      name: user.fullName,
      role: user.role,
      teamId: user.teamId,
    };
  }
}
