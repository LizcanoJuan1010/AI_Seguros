import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { timingSafeEqual } from 'crypto';
import type { Request } from 'express';

const SECRET_HEADER = 'x-webhook-secret';

/**
 * Guard del webhook de inicio de llamada (POST /elevenlabs/init). A
 * diferencia del post-call (firma HMAC sobre el body), este webhook de
 * ElevenLabs se autentica con un header simple cuyo nombre y valor tú
 * defines en el dashboard de ElevenLabs al configurarlo (ver "Twilio
 * personalization" — no hay un nombre de header fijo del lado de
 * ElevenLabs, es 100% configurable). Usamos `x-webhook-secret` por
 * consistencia con el mismo patrón ya usado para el gateway de WhatsApp.
 */
@Injectable()
export class ElevenLabsInitGuard implements CanActivate {
  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();
    const header = request.headers[SECRET_HEADER];
    const provided = Array.isArray(header) ? header[0] : header;

    const secret = this.config.get<string>('ELEVENLABS_WEBHOOK_SECRET');
    if (!secret) {
      throw new UnauthorizedException(
        'ELEVENLABS_WEBHOOK_SECRET no está configurado',
      );
    }
    if (!provided) {
      throw new UnauthorizedException(`Falta el header ${SECRET_HEADER}`);
    }

    const expected = Buffer.from(secret, 'utf8');
    const got = Buffer.from(provided, 'utf8');
    const valid = expected.length === got.length && timingSafeEqual(expected, got);
    if (!valid) {
      throw new UnauthorizedException(`${SECRET_HEADER} inválido`);
    }

    return true;
  }
}
