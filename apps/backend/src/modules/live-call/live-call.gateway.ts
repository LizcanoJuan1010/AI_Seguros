import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  WebSocketGateway,
} from '@nestjs/websockets';
import WebSocket from 'ws';
import { CallStatus } from '../../generated/prisma/enums';
import { LiveCallService } from './live-call.service';

const AUTH_TIMEOUT_MS = 10_000;

/** Mismo shape que `AccessTokenClaims` de jwt-auth.guard.ts (no se exporta
 * desde ahí — cada consumidor de JwtService declara el suyo, es el patrón
 * ya establecido en este backend). */
interface AccessTokenClaims {
  sub: string;
  email: string;
  role?: string;
  teamId?: string | null;
  type?: string;
}

interface JsonFrame {
  type?: string;
  data?: Record<string, unknown>;
}

/** `ws` entrega binario como Buffer | ArrayBuffer | Buffer[] (fragmentado) —
 * normaliza siempre a un único Buffer antes de reenviar o de-serializar. */
function toBuffer(raw: WebSocket.RawData): Buffer {
  if (Array.isArray(raw)) return Buffer.concat(raw);
  if (Buffer.isBuffer(raw)) return raw;
  return Buffer.from(raw);
}

function parseJsonFrame(raw: WebSocket.RawData): JsonFrame | null {
  try {
    return JSON.parse(toBuffer(raw).toString('utf8')) as JsonFrame;
  } catch {
    return null;
  }
}

function stringField(
  data: Record<string, unknown> | undefined,
  key: string,
): string {
  const value = data?.[key];
  return typeof value === 'string' ? value.trim() : '';
}

/**
 * Gateway WS de la llamada en vivo (`/api/v1/live-call`). Requiere el
 * WsAdapter de `@nestjs/platform-ws` (ver main.ts) — el adapter socket.io
 * por defecto de NestJS envuelve los mensajes en su propio protocolo y
 * rompería el relay de audio binario byte-a-byte que pide el diseño.
 *
 * Terminación de auth: NO usa `@SubscribeMessage` (ese mecanismo espera
 * frames `{event,data}` del WsAdapter, y nuestro protocolo ya usa
 * `{type,data}` en todo el stack — Python incluido). En cambio, cada
 * conexión se envuelve en un `LiveCallRelay` que lee el socket `ws` crudo
 * directo, igual que `VoiceSession` del lado Python.
 */
@WebSocketGateway({ path: '/api/v1/live-call' })
@Injectable()
export class LiveCallGateway
  implements OnGatewayConnection, OnGatewayDisconnect
{
  private readonly logger = new Logger(LiveCallGateway.name);
  private readonly relays = new WeakMap<WebSocket, LiveCallRelay>();

  constructor(
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly liveCallService: LiveCallService,
  ) {}

  handleConnection(client: WebSocket): void {
    const relay = new LiveCallRelay(
      client,
      this.jwt,
      this.config,
      this.liveCallService,
      this.logger,
    );
    this.relays.set(client, relay);
    relay.start();
  }

  handleDisconnect(client: WebSocket): void {
    this.relays.get(client)?.handleClientDisconnect();
  }
}

/**
 * Estado de UNA conexión: auth -> dial saliente a Python -> relay crudo en
 * ambas direcciones -> espía transcript_final/turn_end para persistir ->
 * cierre en cascada con el mapeo de estado (mirror de `mapCallStatus` en
 * elevenlabs.service.ts, adaptado a señales de WebSocket en vez de webhook).
 */
export class LiveCallRelay {
  private pythonSocket: WebSocket | null = null;
  private aiCallId: string | null = null;
  private tenantId: string | null = null;
  private turnsCompleted = 0;
  private authTimer: NodeJS.Timeout | null = null;
  private closed = false;

  constructor(
    private readonly client: WebSocket,
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly liveCallService: LiveCallService,
    private readonly logger: Logger,
  ) {}

  start(): void {
    this.authTimer = setTimeout(() => {
      this.rejectAuth('timeout esperando el frame de autenticación');
    }, AUTH_TIMEOUT_MS);
    this.client.once('message', (raw, isBinary) => {
      void this.handleFirstMessage(raw, isBinary);
    });
  }

  private async handleFirstMessage(
    raw: WebSocket.RawData,
    isBinary: boolean,
  ): Promise<void> {
    if (this.authTimer) clearTimeout(this.authTimer);
    if (isBinary) {
      this.rejectAuth('se esperaba el frame "auth" (JSON), no audio');
      return;
    }

    let claims: AccessTokenClaims;
    let rawToken = '';
    try {
      const msg = parseJsonFrame(raw);
      if (msg?.type !== 'auth') {
        throw new Error("se esperaba el frame 'auth' primero");
      }
      rawToken = stringField(msg.data, 'token');
      claims = await this.jwt.verifyAsync<AccessTokenClaims>(rawToken);
      if (claims.type !== 'access') {
        throw new Error('tipo de token inválido');
      }
    } catch {
      this.rejectAuth('token inválido o expirado');
      return;
    }

    this.tenantId = claims.teamId ?? '';

    try {
      await this.connectPython(rawToken);
    } catch (err) {
      this.logger.warn(
        `no se pudo conectar al servicio de voz: ${String(err)}`,
      );
      this.sendJson('error', { message: 'Servicio de voz no disponible' });
      this.client.close(1011);
      return;
    }

    try {
      this.aiCallId = await this.liveCallService.openSession(
        this.tenantId,
        claims.sub,
      );
    } catch (err) {
      this.logger.error(
        `no se pudo abrir la sesión de la llamada: ${String(err)}`,
      );
      this.sendJson('error', { message: 'No se pudo abrir la sesión' });
      this.client.close(1011);
      return;
    }

    this.sendJson('auth_ok', {});
    this.client.on('message', (raw2, isBinary2) =>
      this.relayClientMessage(raw2, isBinary2),
    );
  }

  private rejectAuth(reason: string): void {
    this.sendJson('auth_error', { reason });
    this.client.close(4401);
  }

  private async connectPython(rawToken: string): Promise<void> {
    // Mismo host que AI_SERVICE_URL (HTTP) — el servicio Python expone el
    // WS en el mismo puerto, solo cambia el esquema.
    const httpBase =
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://seguria-ai:8085';
    const wsBase = httpBase.replace(/^http/, 'ws');
    const socket = new WebSocket(`${wsBase}/ws/voice/live`);
    this.pythonSocket = socket;

    await new Promise<void>((resolve, reject) => {
      socket.once('open', () => resolve());
      socket.once('error', reject);
    });

    socket.send(JSON.stringify({ type: 'auth', data: { token: rawToken } }));
    await new Promise<void>((resolve, reject) => {
      socket.once('message', (raw) => {
        const msg = parseJsonFrame(raw);
        if (msg?.type === 'auth_ok') {
          resolve();
        } else {
          reject(
            new Error(
              stringField(msg?.data, 'reason') ||
                'auth rechazada por el servicio de voz',
            ),
          );
        }
      });
      socket.once('error', reject);
    });

    socket.on('message', (raw, isBinary) =>
      this.relayPythonMessage(raw, isBinary),
    );
    socket.on('close', () => this.handlePythonDisconnect());
    socket.on('error', (err) =>
      this.logger.warn(
        `error en el socket hacia el servicio de voz: ${String(err)}`,
      ),
    );
  }

  private relayClientMessage(raw: WebSocket.RawData, isBinary: boolean): void {
    if (this.closed || this.pythonSocket?.readyState !== WebSocket.OPEN) return;
    if (isBinary) {
      this.pythonSocket.send(toBuffer(raw));
      return;
    }
    this.pythonSocket.send(toBuffer(raw).toString('utf8'));
    const msg = parseJsonFrame(raw);
    if (msg?.type === 'end_call') {
      void this.finalize(CallStatus.COMPLETADA);
    }
  }

  private relayPythonMessage(raw: WebSocket.RawData, isBinary: boolean): void {
    if (this.closed || this.client.readyState !== WebSocket.OPEN) return;
    if (isBinary) {
      this.client.send(toBuffer(raw));
      return;
    }
    this.client.send(toBuffer(raw).toString('utf8'));
    this.peekForPersistence(raw);
  }

  /** Espía (sin bloquear el relay) los dos eventos que necesitan quedar en
   * Postgres — el resto de los frames pasan de largo sin que Nest los mire. */
  private peekForPersistence(raw: WebSocket.RawData): void {
    if (!this.aiCallId || !this.tenantId) return;
    const msg = parseJsonFrame(raw);
    if (!msg) return;
    const aiCallId = this.aiCallId;
    const tenantId = this.tenantId;
    if (msg.type === 'transcript_final') {
      const content = stringField(msg.data, 'text');
      if (content) {
        this.liveCallService
          .recordClientTurn(tenantId, aiCallId, content)
          .catch((err: unknown) =>
            this.logger.warn(
              `no se pudo persistir el turno del cliente: ${String(err)}`,
            ),
          );
      }
    } else if (msg.type === 'turn_end') {
      this.turnsCompleted += 1;
      const content = stringField(msg.data, 'reply_text');
      if (content) {
        this.liveCallService
          .recordAssistantTurn(tenantId, aiCallId, content)
          .catch((err: unknown) =>
            this.logger.warn(
              `no se pudo persistir el turno de la IA: ${String(err)}`,
            ),
          );
      }
    }
  }

  /** Cierre del lado navegador (colgó, se cayó la red, cerró la pestaña).
   * Si ya se finalizó por un `end_call` explícito, `finalize` es un no-op. */
  handleClientDisconnect(): void {
    if (this.closed) return;
    this.closed = true;
    if (this.authTimer) clearTimeout(this.authTimer);
    this.pythonSocket?.close();
    void this.finalize(CallStatus.ABANDONADA);
  }

  /** Cierre del lado Python/Deepgram (falla interna) — la llamada nunca
   * debería quedar en curso si el motor de voz se cayó a mitad de camino. */
  private handlePythonDisconnect(): void {
    if (this.closed) return;
    this.closed = true;
    this.sendJson('error', {
      message: 'Se perdió la conexión con el servicio de voz',
    });
    void this.finalize(CallStatus.FALLIDA);
    if (this.client.readyState === WebSocket.OPEN) {
      this.client.close(1011);
    }
  }

  private async finalize(status: CallStatus): Promise<void> {
    if (!this.aiCallId || !this.tenantId) return;
    const aiCallId = this.aiCallId;
    const tenantId = this.tenantId;
    this.aiCallId = null; // guarda contra doble finalize (end_call + disconnect posterior)
    try {
      await this.liveCallService.finalizeCall(tenantId, aiCallId, status);
      this.sendJson('call_status', { status });
    } catch (err) {
      this.logger.error(
        `no se pudo finalizar la llamada ${aiCallId}: ${String(err)}`,
      );
    }
  }

  private sendJson(type: string, data: Record<string, unknown>): void {
    if (this.client.readyState === WebSocket.OPEN) {
      this.client.send(JSON.stringify({ type, data }));
    }
  }
}
