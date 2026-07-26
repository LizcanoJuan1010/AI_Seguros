import { EventEmitter } from 'events';
import { Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { JwtService } from '@nestjs/jwt';
import WebSocket from 'ws';
import { CallStatus } from '../../generated/prisma/enums';
import { LiveCallGateway, LiveCallRelay } from './live-call.gateway';
import { LiveCallService } from './live-call.service';

/** Doble de `ws.WebSocket`: mismo protocolo basado en EventEmitter que usa
 * LiveCallRelay (`.once/.on('message'|'close', ...)`, `.send`, `.close`,
 * `.readyState`) — sin abrir ningún socket real. */
class FakeSocket extends EventEmitter {
  readyState: number = WebSocket.OPEN;
  sent: Array<string | Buffer> = [];
  closedCode: number | undefined;

  send(data: string | Buffer): void {
    this.sent.push(data);
  }

  close(code?: number): void {
    this.closedCode = code;
    this.readyState = WebSocket.CLOSED;
  }

  jsonMessages(): Array<{ type?: string; data?: Record<string, unknown> }> {
    return this.sent
      .filter((d): d is string => typeof d === 'string')
      .map(
        (d) =>
          JSON.parse(d) as { type?: string; data?: Record<string, unknown> },
      );
  }
}

/** Acceso tipado a los campos/métodos privados de LiveCallRelay — evita
 * mockear el socket saliente a Python solo para probar el mapeo de estado
 * y la persistencia por espionaje de frames (eso ya corre en tests aparte). */
interface RelayInternals {
  aiCallId: string | null;
  tenantId: string | null;
  pythonSocket: WebSocket | null;
  finalize(status: CallStatus): Promise<void>;
  peekForPersistence(raw: WebSocket.RawData): void;
  relayClientMessage(raw: WebSocket.RawData, isBinary: boolean): void;
  handlePythonDisconnect(): void;
}

function internals(relay: LiveCallRelay): RelayInternals {
  return relay as unknown as RelayInternals;
}

function makeRelay() {
  const client = new FakeSocket();
  const jwt = { verifyAsync: jest.fn() } as unknown as JwtService;
  const config = { get: jest.fn() } as unknown as ConfigService;
  const liveCallService = {
    openSession: jest.fn().mockResolvedValue('call-id'),
    recordClientTurn: jest.fn().mockResolvedValue(undefined),
    recordAssistantTurn: jest.fn().mockResolvedValue(undefined),
    finalizeCall: jest.fn().mockResolvedValue(undefined),
  } as unknown as LiveCallService;
  const logger = {
    warn: jest.fn(),
    error: jest.fn(),
    log: jest.fn(),
  } as unknown as Logger;
  // Doble del gateway: solo lo que el relay le pide (los cupos anónimos).
  // `reservarCupoAnon` devuelve true por defecto; los tests que prueban el
  // tope lo sobreescriben.
  const gateway = {
    reservarCupoAnon: jest.fn().mockReturnValue(true),
    liberarCupoAnon: jest.fn(),
  } as unknown as LiveCallGateway;
  const relay = new LiveCallRelay(
    client as unknown as WebSocket,
    jwt,
    config,
    liveCallService,
    logger,
    gateway,
  );
  return { relay, client, jwt, config, liveCallService, gateway };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

describe('LiveCallRelay — auth', () => {
  it('rechaza la conexión si el primer frame no es "auth"', async () => {
    const { relay, client } = makeRelay();
    relay.start();

    client.emit(
      'message',
      Buffer.from(JSON.stringify({ type: 'mute' })),
      false,
    );
    await tick();

    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({ type: 'auth_error' });
    expect(client.closedCode).toBe(4401);
  });

  it('rechaza un JWT inválido sin intentar abrir el socket de Python', async () => {
    const { relay, client, jwt, config } = makeRelay();
    (jwt.verifyAsync as jest.Mock).mockRejectedValue(new Error('bad token'));
    relay.start();

    client.emit(
      'message',
      Buffer.from(JSON.stringify({ type: 'auth', data: { token: 'bad' } })),
      false,
    );
    await tick();

    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({ type: 'auth_error' });
    expect(client.closedCode).toBe(4401);
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(config.get).not.toHaveBeenCalled();
  });

  it('rechaza si el primer frame llega binario en vez de JSON', async () => {
    const { relay, client } = makeRelay();
    relay.start();

    client.emit('message', Buffer.from([1, 2, 3]), true);
    await tick();

    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({ type: 'auth_error' });
    expect(client.closedCode).toBe(4401);
  });
});

/** El cliente final entra sin JWT: la landing enlaza /llamada directo y su
 *  identidad es el device_id anónimo del navegador. */
describe('LiveCallRelay — auth anónima por device_id', () => {
  const authAnon = (relay: LiveCallRelay, client: FakeSocket, deviceId: string) => {
    relay.start();
    client.emit(
      'message',
      Buffer.from(JSON.stringify({ type: 'auth', data: { device_id: deviceId } })),
      false,
    );
  };

  it('rechaza un device_id con formato inválido sin tocar Python', async () => {
    const { relay, client, config } = makeRelay();
    authAnon(relay, client, 'no-soy-un-device-id');
    await tick();

    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({ type: 'auth_error' });
    expect(client.closedCode).toBe(4401);
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(config.get).not.toHaveBeenCalled();
  });

  it('rechaza si el dispositivo ya tiene una llamada en curso', async () => {
    const { relay, client, gateway, config } = makeRelay();
    (gateway.reservarCupoAnon as jest.Mock).mockReturnValue(false);
    authAnon(relay, client, 'dev_11111111-2222-3333-4444-555555555555');
    await tick();

    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({
      type: 'auth_error',
      data: { reason: expect.stringContaining('llamada en curso') },
    });
    expect(client.closedCode).toBe(4401);
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(config.get).not.toHaveBeenCalled();
  });

  it('un device_id válido reserva cupo e intenta abrir el socket a Python', async () => {
    const { relay, client, gateway, config } = makeRelay();
    const deviceId = 'dev_11111111-2222-3333-4444-555555555555';
    authAnon(relay, client, deviceId);
    await tick();

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(gateway.reservarCupoAnon).toHaveBeenCalledWith(deviceId);
    // Llegó hasta el dial a Python (que en el test falla y cierra con 1011):
    // lo que importa es que la auth NO lo rechazó con 4401.
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(config.get).toHaveBeenCalled();
    expect(client.closedCode).not.toBe(4401);
  });

  it('devuelve el cupo al cerrarse, y una sola vez', () => {
    const { relay, client, gateway } = makeRelay();
    const deviceId = 'dev_11111111-2222-3333-4444-555555555555';
    authAnon(relay, client, deviceId);

    relay.handleClientDisconnect();
    relay.handleClientDisconnect();
    internals(relay).handlePythonDisconnect();

    // Sin la idempotencia, un cierre en cascada descontaría de más y el
    // dispositivo quedaría con cupos negativos (o bloqueado para siempre).
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(gateway.liberarCupoAnon).toHaveBeenCalledTimes(1);
    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(gateway.liberarCupoAnon).toHaveBeenCalledWith(deviceId);
  });
});

describe('LiveCallGateway — topes de llamadas anónimas simultáneas', () => {
  const nuevo = () =>
    new LiveCallGateway(
      { verifyAsync: jest.fn() } as unknown as JwtService,
      { get: jest.fn() } as unknown as ConfigService,
      {} as unknown as LiveCallService,
    );

  it('un mismo dispositivo no abre dos llamadas a la vez', () => {
    const gw = nuevo();
    expect(gw.reservarCupoAnon('dev_a')).toBe(true);
    expect(gw.reservarCupoAnon('dev_a')).toBe(false);
  });

  it('liberar el cupo permite volver a llamar', () => {
    const gw = nuevo();
    gw.reservarCupoAnon('dev_a');
    gw.liberarCupoAnon('dev_a');
    expect(gw.reservarCupoAnon('dev_a')).toBe(true);
  });

  it('dispositivos distintos no se bloquean entre sí', () => {
    const gw = nuevo();
    expect(gw.reservarCupoAnon('dev_a')).toBe(true);
    expect(gw.reservarCupoAnon('dev_b')).toBe(true);
  });

  it('hay un techo global aunque cada dispositivo sea distinto', () => {
    const gw = nuevo();
    for (let i = 0; i < 25; i++) {
      expect(gw.reservarCupoAnon(`dev_${i}`)).toBe(true);
    }
    expect(gw.reservarCupoAnon('dev_uno_mas')).toBe(false);
  });
});

describe('LiveCallRelay — cierre en cascada y mapeo de estado', () => {
  it('end_call explícito con sesión activa -> COMPLETADA', async () => {
    const { relay, client, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-1';
    internals(relay).tenantId = 'tenant-1';
    const fakePython = new FakeSocket();
    internals(relay).pythonSocket = fakePython;
    internals(relay).relayClientMessage(
      Buffer.from(JSON.stringify({ type: 'end_call' })),
      false,
    );
    await tick();

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.finalizeCall).toHaveBeenCalledWith(
      'tenant-1',
      'call-1',
      CallStatus.COMPLETADA,
    );
    const messages = client.jsonMessages();
    expect(messages[messages.length - 1]).toMatchObject({
      type: 'call_status',
      data: { status: CallStatus.COMPLETADA },
    });
  });

  it('corte del lado navegador sin end_call -> ABANDONADA', async () => {
    const { relay, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-2';
    internals(relay).tenantId = 'tenant-1';

    relay.handleClientDisconnect();
    await tick();

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.finalizeCall).toHaveBeenCalledWith(
      'tenant-1',
      'call-2',
      CallStatus.ABANDONADA,
    );
  });

  it('caída del lado del servicio de voz (Python) -> FALLIDA', async () => {
    const { relay, client, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-3';
    internals(relay).tenantId = 'tenant-1';
    internals(relay).handlePythonDisconnect();
    await tick();

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.finalizeCall).toHaveBeenCalledWith(
      'tenant-1',
      'call-3',
      CallStatus.FALLIDA,
    );
    expect(client.jsonMessages().some((m) => m.type === 'error')).toBe(true);
  });

  it('finalize es un no-op si la llamada ya se finalizó (guarda contra doble finalize)', async () => {
    const { relay, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-4';
    internals(relay).tenantId = 'tenant-1';
    await internals(relay).finalize(CallStatus.COMPLETADA);
    await internals(relay).finalize(CallStatus.FALLIDA);

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.finalizeCall).toHaveBeenCalledTimes(1);
  });
});

describe('LiveCallRelay — persistencia por espionaje de frames', () => {
  it('transcript_final persiste el turno del cliente', () => {
    const { relay, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-5';
    internals(relay).tenantId = 'tenant-1';
    internals(relay).peekForPersistence(
      Buffer.from(
        JSON.stringify({ type: 'transcript_final', data: { text: 'hola' } }),
      ),
    );

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.recordClientTurn).toHaveBeenCalledWith(
      'tenant-1',
      'call-5',
      'hola',
    );
  });

  it('turn_end persiste el turno de la IA', () => {
    const { relay, liveCallService } = makeRelay();
    internals(relay).aiCallId = 'call-6';
    internals(relay).tenantId = 'tenant-1';
    internals(relay).peekForPersistence(
      Buffer.from(
        JSON.stringify({ type: 'turn_end', data: { reply_text: 'con gusto' } }),
      ),
    );

    // eslint-disable-next-line @typescript-eslint/unbound-method
    expect(liveCallService.recordAssistantTurn).toHaveBeenCalledWith(
      'tenant-1',
      'call-6',
      'con gusto',
    );
  });
});
