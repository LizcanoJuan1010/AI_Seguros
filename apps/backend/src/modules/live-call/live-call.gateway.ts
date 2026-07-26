import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import {
  OnGatewayConnection,
  OnGatewayDisconnect,
  WebSocketGateway,
} from '@nestjs/websockets';
import WebSocket from 'ws';
import { DEMO_TENANT_ID } from '../../common/tenant.decorator';
import { CallStatus } from '../../generated/prisma/enums';
import { LiveCallService } from './live-call.service';

const AUTH_TIMEOUT_MS = 10_000;
const PYTHON_HANDSHAKE_TIMEOUT_MS = 8_000;
// Cada 30 s sin pong el cliente se da por muerto. Sin heartbeat, un TCP que
// muere sin FIN (laptop suspendida, cambio de red móvil) dejaba el relay, el
// socket a Python y la sesión de Deepgram vivos Y FACTURANDO — y con
// MAX_ANON_POR_DISPOSITIVO=1, ese device quedaba sin poder volver a llamar
// hasta que nginx cortara por proxy_read_timeout: una hora.
const HEARTBEAT_MS = 30_000;

/** Promise con techo: `ws` no emite nada en varios modos de colgada (upgrade
 *  que no completa, servidor que no contesta) y el timeout de connect del SO
 *  (~130 s) no aplica una vez el TCP conectó. */
function conTimeout<T>(p: Promise<T>, ms: number, que: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(`timeout ${que} (${ms}ms)`)), ms);
    t.unref?.();
    p.then(
      (v) => {
        clearTimeout(t);
        resolve(v);
      },
      (e: unknown) => {
        clearTimeout(t);
        reject(e instanceof Error ? e : new Error(String(e)));
      },
    );
  });
}

// El cliente final NO tiene usuario: su identidad es el `device_id` anónimo
// del navegador (lib/clientIdentity.ts), el mismo que ya ancla memoria y leads
// en el chat web. Se acepta como alternativa al JWT porque la landing enlaza
// /llamada directo y un lead no debería tener que loguearse para hablar.
//
// Eso deja el WS abierto a cualquiera, y cada minuto cuesta Deepgram: el freno
// es un tope de conexiones SIMULTÁNEAS por dispositivo y global. No sustituye
// a un rate limit real por ventana de tiempo — un mismo device_id puede abrir
// y cerrar llamadas en serie sin límite. Endurecer eso es trabajo aparte (el
// gancho natural es Redis, que ya está en el stack).
const MAX_ANON_POR_DISPOSITIVO = 1;
const MAX_ANON_TOTAL = 25;
// Formato que emite `freshId()` en lib/clientIdentity.ts: `dev_<uuid|rand>`.
const DEVICE_ID_RE = /^dev_[A-Za-z0-9-]{8,64}$/;

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
  /** Llamadas anónimas abiertas ahora mismo, por device_id (ver los topes). */
  private readonly anonAbiertas = new Map<string, number>();

  constructor(
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly liveCallService: LiveCallService,
  ) {}

  /** Reserva un cupo anónimo; false si el dispositivo (o el servicio) topó. */
  reservarCupoAnon(deviceId: string): boolean {
    const total = [...this.anonAbiertas.values()].reduce((a, b) => a + b, 0);
    const delDispositivo = this.anonAbiertas.get(deviceId) ?? 0;
    if (total >= MAX_ANON_TOTAL || delDispositivo >= MAX_ANON_POR_DISPOSITIVO) {
      return false;
    }
    this.anonAbiertas.set(deviceId, delDispositivo + 1);
    return true;
  }

  liberarCupoAnon(deviceId: string): void {
    const quedan = (this.anonAbiertas.get(deviceId) ?? 1) - 1;
    if (quedan > 0) this.anonAbiertas.set(deviceId, quedan);
    else this.anonAbiertas.delete(deviceId);
  }

  handleConnection(client: WebSocket): void {
    const relay = new LiveCallRelay(
      client,
      this.jwt,
      this.config,
      this.liveCallService,
      this.logger,
      this,
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
  /** device_id si la llamada es anónima (para devolver el cupo al cerrar). */
  private anonDeviceId: string | null = null;
  private heartbeat: NodeJS.Timeout | null = null;
  private pongPendiente = false;

  constructor(
    private readonly client: WebSocket,
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
    private readonly liveCallService: LiveCallService,
    private readonly logger: Logger,
    private readonly gateway: LiveCallGateway,
  ) {}

  start(): void {
    this.authTimer = setTimeout(() => {
      this.rejectAuth('timeout esperando el frame de autenticación');
    }, AUTH_TIMEOUT_MS);
    // Detección de cliente muerto (ver HEARTBEAT_MS). terminate() y no
    // close(): un peer que no contesta pongs tampoco va a completar el
    // handshake de cierre. unref: que un timer vivo no retenga el proceso.
    this.client.on('pong', () => {
      this.pongPendiente = false;
    });
    this.heartbeat = setInterval(() => {
      if (this.client.readyState !== WebSocket.OPEN) return;
      if (this.pongPendiente) {
        this.logger.warn('cliente sin pong: terminando la llamada');
        this.client.terminate();
        return;
      }
      this.pongPendiente = true;
      this.client.ping();
    }, HEARTBEAT_MS);
    this.heartbeat.unref?.();
    this.client.once('message', (raw, isBinary) => {
      void this.handleFirstMessage(raw, isBinary);
    });
  }

  private pararHeartbeat(): void {
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
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

    // Dos identidades posibles: staff con JWT, o cliente final anónimo con el
    // `device_id` del navegador. El token gana si viene: un gerente probando
    // desde el dashboard debe quedar atado a SU tenant, no al demo.
    let rawToken = '';
    let deviceId = '';
    let userSub = '';
    try {
      const msg = parseJsonFrame(raw);
      if (msg?.type !== 'auth') {
        throw new Error("se esperaba el frame 'auth' primero");
      }
      rawToken = stringField(msg.data, 'token');
    } catch {
      rawToken = '';
    }

    if (rawToken) {
      let claims: AccessTokenClaims;
      try {
        claims = await this.jwt.verifyAsync<AccessTokenClaims>(rawToken);
        if (claims.type !== 'access') {
          throw new Error('tipo de token inválido');
        }
      } catch {
        this.rejectAuth('token inválido o expirado');
        return;
      }
      this.tenantId = claims.teamId ?? '';
      userSub = claims.sub;
    } else {
      try {
        deviceId = stringField(parseJsonFrame(raw)?.data, 'device_id');
      } catch {
        deviceId = '';
      }
      if (!DEVICE_ID_RE.test(deviceId)) {
        this.rejectAuth('falta token o device_id válido');
        return;
      }
      if (!this.gateway.reservarCupoAnon(deviceId)) {
        this.rejectAuth(
          'ya hay una llamada en curso desde este dispositivo; ' +
            'ciérrala antes de iniciar otra',
        );
        return;
      }
      this.anonDeviceId = deviceId;
      this.tenantId = DEMO_TENANT_ID;
      userSub = deviceId;
    }

    try {
      await this.connectPython(rawToken, deviceId);
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
        userSub,
      );
    } catch (err) {
      // Degradar, no tumbar: la voz (navegador->Nest->Python->Deepgram) no
      // necesita Postgres. Con aiCallId=null, peekForPersistence y finalize
      // ya hacen no-op solos — la llamada corre, solo no queda el transcript
      // en el CRM. La memoria del lado Python es independiente.
      this.logger.error(
        `llamada sin persistencia (openSession falló): ${String(err)}`,
      );
      this.aiCallId = null;
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

  private async connectPython(
    rawToken: string,
    deviceId: string,
  ): Promise<void> {
    // Una sola salida a Python por relay. Si se reintenta, cierra la anterior.
    if (this.pythonSocket) {
      this.pythonSocket.removeAllListeners();
      this.pythonSocket.close();
      this.pythonSocket = null;
    }

    const httpBase =
      // Mismo default que elevenlabs.service/campaigns.service: dentro de
      // Docker, `localhost` sería el propio contenedor de Nest.
      this.config.get<string>('AI_SERVICE_URL') ?? 'http://seguria-ai:8085';
    const wsBase = httpBase.replace(/^http/, 'ws');
    const socket = new WebSocket(`${wsBase}/ws/voice/live`);
    this.pythonSocket = socket;
    try {
      // Con timeout los DOS pasos: un Python que acepta el TCP pero nunca
      // completa el upgrade (o nunca contesta auth_ok) no dispara 'open' ni
      // 'error' JAMÁS — sin esto el relay quedaba colgado para siempre, el
      // usuario en "Conectando…" y el cupo anónimo reservado.
      await conTimeout(
        new Promise<void>((resolve, reject) => {
          socket.once('open', () => resolve());
          socket.once('error', reject);
        }),
        PYTHON_HANDSHAKE_TIMEOUT_MS,
        'abriendo el WS al servicio de voz',
      );

      // Python autentica igual que acá: token de staff, o device_id anónimo.
      socket.send(
        JSON.stringify({
          type: 'auth',
          data: rawToken ? { token: rawToken } : { device_id: deviceId },
        }),
      );
      await conTimeout(
        new Promise<void>((resolve, reject) => {
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
        }),
        PYTHON_HANDSHAKE_TIMEOUT_MS,
        'esperando auth_ok del servicio de voz',
      );
    } catch (err) {
      // El socket colgado no se cierra solo: sin esto quedaba vivo apuntado
      // por this.pythonSocket (Python lo mataría a los ~10 s por su timeout
      // de auth, pero mejor no depender del otro lado).
      socket.removeAllListeners();
      socket.close();
      this.pythonSocket = null;
      throw err;
    }

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
  /** Devuelve el cupo anónimo. Idempotente a propósito: se llama desde TODAS
   *  las rutas de cierre (cliente, Python, rechazo de auth) y sin esto un
   *  dispositivo quedaría bloqueado para siempre tras una caída. */
  private liberarCupo(): void {
    if (!this.anonDeviceId) return;
    this.gateway.liberarCupoAnon(this.anonDeviceId);
    this.anonDeviceId = null;
  }

  handleClientDisconnect(): void {
    this.liberarCupo();
    this.pararHeartbeat();
    if (this.closed) return;
    this.closed = true;
    if (this.authTimer) clearTimeout(this.authTimer);
    this.pythonSocket?.close();
    void this.finalize(CallStatus.ABANDONADA);
  }

  /** Cierre del lado Python/Deepgram (falla interna) — la llamada nunca
   * debería quedar en curso si el motor de voz se cayó a mitad de camino. */
  private handlePythonDisconnect(): void {
    this.liberarCupo();
    this.pararHeartbeat();
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
