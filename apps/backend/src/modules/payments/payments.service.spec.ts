import {
  BadRequestException,
  UnauthorizedException,
} from '@nestjs/common';
import { createHmac } from 'crypto';
import { PrismaService } from '../../prisma/prisma.service';
import { PaymentStatus } from '../../generated/prisma/enums';
import { PolarClient } from './polar.client';
import { PaymentsService } from './payments.service';

describe('PaymentsService', () => {
  const payment = {
    upsert: jest.fn(),
    findUnique: jest.fn(),
    findFirst: jest.fn(),
    update: jest.fn(),
  };
  const prisma = { payment } as unknown as PrismaService;
  const polar = {
    isConfigured: jest.fn(),
    createCheckout: jest.fn(),
  } as unknown as PolarClient;
  const service = new PaymentsService(prisma, polar);

  const TENANT = '11111111-1111-1111-1111-111111111111';

  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.POLAR_ACCESS_TOKEN;
    delete process.env.POLAR_WEBHOOK_SECRET;
  });

  describe('createCheckout', () => {
    it('modo demo sin token: no llama Polar y persiste provider=demo', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(false);
      payment.upsert.mockResolvedValue({
        reference: 'SEG-ABC',
        checkoutUrl: null,
        linkId: 'demo-SEG-ABC',
        provider: 'demo',
        status: PaymentStatus.PENDING,
        amountCop: 50000,
        concept: 'Prima',
      });

      const result = await service.createCheckout(TENANT, {
        amountCop: 50000,
        concept: 'Prima',
      });

      expect(polar.createCheckout).not.toHaveBeenCalled();
      expect(payment.upsert).toHaveBeenCalled();
      const [{ create }] = payment.upsert.mock.calls[0] as unknown as [
        { create: { teamId: string; provider: string; linkId: string } },
      ];
      expect(create.teamId).toBe(TENANT);
      expect(create.provider).toBe('demo');
      expect(create.linkId).toMatch(/^demo-SEG-/);
      expect(result.demo).toBe(true);
      expect(result.provider).toBe('demo');
      expect(result.checkoutUrl).toBeNull();
    });

    it('con token: llama Polar mock y guarda checkoutUrl', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(true);
      (polar.createCheckout as jest.Mock).mockResolvedValue({
        checkoutId: 'chk_1',
        checkoutUrl: 'https://sandbox.polar.sh/checkout/chk_1',
      });
      payment.upsert.mockResolvedValue({
        reference: 'SEG-XYZ',
        checkoutUrl: 'https://sandbox.polar.sh/checkout/chk_1',
        linkId: 'chk_1',
        provider: 'polar',
        status: PaymentStatus.PENDING,
        amountCop: 99000,
        concept: 'Vida',
      });

      const result = await service.createCheckout(TENANT, {
        amountCop: 99000,
        concept: 'Vida',
        sessionKey: 't:web:1',
      });

      expect(polar.createCheckout).toHaveBeenCalledWith(
        99000,
        'Vida',
        expect.stringMatching(/^SEG-/),
      );
      expect(result.demo).toBe(false);
      expect(result.checkoutUrl).toContain('polar.sh');
      expect(result.linkId).toBe('chk_1');
    });

    it('rechaza amountCop inválido sin llamar Polar', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(true);
      await expect(
        service.createCheckout(TENANT, { amountCop: 0 }),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(polar.createCheckout).not.toHaveBeenCalled();
      expect(payment.upsert).not.toHaveBeenCalled();
    });

    it('rechaza tenant vacío', async () => {
      await expect(
        service.createCheckout('  ', { amountCop: 1000 }),
      ).rejects.toBeInstanceOf(BadRequestException);
      expect(payment.upsert).not.toHaveBeenCalled();
    });
  });

  describe('handleWebhook', () => {
    function sign(
      secret: string,
      id: string,
      ts: string,
      body: string,
    ): string {
      const sig = createHmac('sha256', Buffer.from(secret, 'utf8'))
        .update(`${id}.${ts}.${body}`)
        .digest('base64');
      return `v1,${sig}`;
    }

    it('non-demo sin secreto: 401 fail-closed', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(true);
      process.env.POLAR_ACCESS_TOKEN = 'polar_oat_test';
      await expect(
        service.handleWebhook(Buffer.from('{}'), {}, { type: 'order.paid' }),
      ).rejects.toBeInstanceOf(UnauthorizedException);
      expect(payment.update).not.toHaveBeenCalled();
    });

    it('non-demo firma inválida: 401', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(true);
      process.env.POLAR_ACCESS_TOKEN = 'polar_oat_test';
      process.env.POLAR_WEBHOOK_SECRET = 'whsec_test';
      await expect(
        service.handleWebhook(
          Buffer.from('{"type":"order.paid"}'),
          {
            'webhook-id': 'msg_1',
            'webhook-timestamp': '123',
            'webhook-signature': 'v1,invalid',
          },
          { type: 'order.paid', data: {} },
        ),
      ).rejects.toBeInstanceOf(UnauthorizedException);
      expect(payment.update).not.toHaveBeenCalled();
    });

    it('HMAC válido → APPROVED por linkId (sin confiar teamId del body)', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(true);
      process.env.POLAR_ACCESS_TOKEN = 'polar_oat_test';
      process.env.POLAR_WEBHOOK_SECRET = 'whsec_test';
      const body = JSON.stringify({
        type: 'order.paid',
        data: {
          id: 'ord_1',
          checkout_id: 'chk_1',
          metadata: { reference: 'SEG-1' },
          team_id: 'attacker-team',
        },
      });
      const id = 'msg_1';
      const ts = '1710000000';
      payment.findFirst.mockResolvedValue({
        id: 'pay-uuid',
        reference: 'SEG-1',
        status: PaymentStatus.PENDING,
        transactionId: null,
        method: null,
        teamId: TENANT,
      });
      payment.update.mockResolvedValue({});

      const result = await service.handleWebhook(
        Buffer.from(body),
        {
          'webhook-id': id,
          'webhook-timestamp': ts,
          'webhook-signature': sign('whsec_test', id, ts, body),
        },
        JSON.parse(body),
      );

      expect(result).toEqual({ received: true });
      expect(payment.update).toHaveBeenCalledWith({
        where: { id: 'pay-uuid' },
        data: expect.objectContaining({
          status: PaymentStatus.APPROVED,
          transactionId: 'ord_1',
          method: 'card',
        }),
      });
      const updateArg = payment.update.mock.calls[0][0] as {
        data: Record<string, unknown>;
      };
      expect(updateArg.data.teamId).toBeUndefined();
    });

    it('demo sin secreto: acepta unsigned y no falla', async () => {
      (polar.isConfigured as jest.Mock).mockReturnValue(false);
      payment.findFirst.mockResolvedValue(null);
      const result = await service.handleWebhook(
        Buffer.from('{}'),
        {},
        { type: 'order.paid', data: { checkout_id: 'x' } },
      );
      expect(result).toEqual({
        received: true,
        ignored: 'pago no encontrado',
      });
    });
  });
});
