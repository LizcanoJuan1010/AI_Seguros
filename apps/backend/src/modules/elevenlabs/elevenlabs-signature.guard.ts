import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { createHmac, timingSafeEqual } from 'crypto';
import type { Request } from 'express';

const SIGNATURE_HEADER = 'elevenlabs-signature';
// Tolerancia documentada por ElevenLabs para el timestamp de la firma.
const TOLERANCE_SECONDS = 30 * 60;

/**
 * Verifica `ElevenLabs-Signature: t=<unix>,v0=<hex hmac-sha256>` sobre el
 * cuerpo CRUDO (`req.rawBody`, habilitado en main.ts con `rawBody: true`).
 * El hash firmado es `${t}.${rawBody}` con el secreto compartido
 * `ELEVENLABS_WEBHOOK_SECRET`. Primer guard "de terceros" del backend (los
 * demás son JWT propio); análogo conceptual al `require_service` de la API
 * Python, pero criptográfico porque quien llama es un tercero real.
 */
@Injectable()
export class ElevenLabsSignatureGuard implements CanActivate {
  constructor(private readonly config: ConfigService) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context
      .switchToHttp()
      .getRequest<Request & { rawBody?: Buffer }>();

    const header = request.headers[SIGNATURE_HEADER];
    const signature = Array.isArray(header) ? header[0] : header;
    if (!signature) {
      throw new UnauthorizedException('Falta el header ElevenLabs-Signature');
    }

    const parts = Object.fromEntries(
      signature
        .split(',')
        .map((part) => part.split('=') as [string, string | undefined]),
    );
    const timestamp = parts.t;
    const providedHash = parts.v0;
    if (!timestamp || !providedHash) {
      throw new UnauthorizedException(
        'Formato de ElevenLabs-Signature inválido',
      );
    }

    const ageSeconds = Math.abs(
      Math.floor(Date.now() / 1000) - Number(timestamp),
    );
    if (!Number.isFinite(ageSeconds) || ageSeconds > TOLERANCE_SECONDS) {
      throw new UnauthorizedException('Firma de ElevenLabs expirada');
    }

    const secret = this.config.get<string>('ELEVENLABS_WEBHOOK_SECRET');
    if (!secret) {
      throw new UnauthorizedException(
        'ELEVENLABS_WEBHOOK_SECRET no está configurado',
      );
    }

    const rawBody = request.rawBody;
    if (!rawBody) {
      throw new UnauthorizedException(
        'No se pudo leer el cuerpo crudo de la petición',
      );
    }

    const expectedHash = createHmac('sha256', secret)
      .update(`${timestamp}.${rawBody.toString('utf8')}`)
      .digest('hex');

    const expected = Buffer.from(expectedHash, 'utf8');
    const provided = Buffer.from(providedHash, 'utf8');
    const valid =
      expected.length === provided.length &&
      timingSafeEqual(expected, provided);
    if (!valid) {
      throw new UnauthorizedException('Firma de ElevenLabs inválida');
    }

    return true;
  }
}
