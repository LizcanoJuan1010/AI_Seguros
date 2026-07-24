import { createHmac, timingSafeEqual } from 'crypto';
import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { PaymentStatus } from '../../generated/prisma/enums';
import { PrismaService } from '../../prisma/prisma.service';
import { CreatePaymentDto, UpdatePaymentDto } from './payments.dto';

/**
 * Sistema de registro de pagos del cierre autónomo (Polar sandbox o demo).
 *
 * El servicio IA crea el pago al generar el checkout (pending) y lo consulta
 * antes de emitir la póliza. El estado lo actualizan dos caminos que convergen
 * aquí: los webhooks de Polar (fuente primaria — `order.paid`, `order.refunded`,
 * `refund.*`, `checkout.*` — firmados según Standard Webhooks con
 * POLAR_WEBHOOK_SECRET) y el polling de `verificar_pago` cuando el webhook no
 * alcanza a llegar (p. ej. entorno local sin URL pública).
 *
 * Correlación: `linkId` guarda el checkout_id de Polar, `transactionId` el id
 * de la orden y `reference` la referencia SEG-... que viaja en metadata.
 */

type PolarWebhookPayload = {
  type?: string;
  data?: Record<string, unknown>;
};

/** Orden de precedencia: un estado nunca retrocede (webhooks fuera de orden). */
const STATUS_RANK: Record<PaymentStatus, number> = {
  [PaymentStatus.PENDING]: 0,
  [PaymentStatus.DECLINED]: 1,
  [PaymentStatus.ERROR]: 1,
  [PaymentStatus.APPROVED]: 2,
  [PaymentStatus.REFUND_REQUESTED]: 3,
  [PaymentStatus.VOIDED]: 4,
};

@Injectable()
export class PaymentsService {
  private readonly logger = new Logger(PaymentsService.name);

  constructor(private readonly prisma: PrismaService) {}

  /** Upsert por reference: el agente puede reintentar la herramienta sin duplicar. */
  create(tenantId: string, dto: CreatePaymentDto) {
    const amount = new Prisma.Decimal(dto.amountCop);
    return this.prisma.payment.upsert({
      where: { reference: dto.reference },
      create: {
        teamId: tenantId,
        reference: dto.reference,
        provider: dto.provider ?? 'polar',
        linkId: dto.linkId,
        checkoutUrl: dto.checkoutUrl,
        amountCop: amount,
        currency: dto.currency ?? 'COP',
        concept: dto.concept,
        sessionKey: dto.sessionKey,
      },
      update: {
        linkId: dto.linkId,
        checkoutUrl: dto.checkoutUrl,
        amountCop: amount,
        concept: dto.concept,
        updatedAt: new Date(),
      },
    });
  }

  async get(reference: string) {
    const payment = await this.prisma.payment.findUnique({
      where: { reference },
    });
    if (!payment) {
      throw new NotFoundException(`Pago ${reference} no encontrado`);
    }
    return payment;
  }

  async update(reference: string, dto: UpdatePaymentDto) {
    await this.get(reference);
    // Los null del polling (p. ej. transactionId aún desconocido) no deben
    // borrar valores que el webhook ya escribió.
    const data = Object.fromEntries(
      Object.entries(dto).filter(([, v]) => v !== null && v !== undefined),
    );
    return this.prisma.payment.update({
      where: { reference },
      data: { ...data, updatedAt: new Date() },
    });
  }

  /**
   * Webhook de Polar. Siempre responde 200 (aunque el evento se ignore) para
   * cortar los reintentos; la autenticidad se valida con la firma Standard
   * Webhooks (HMAC-SHA256 de `id.timestamp.rawBody` con el secreto).
   */
  async handleWebhook(
    rawBody: Buffer | undefined,
    headers: Record<string, string | string[] | undefined>,
    payload: PolarWebhookPayload,
  ) {
    if (!this.verifySignature(rawBody, headers)) {
      this.logger.warn('webhook de Polar con firma inválida: ignorado');
      return { received: true, ignored: 'firma inválida' };
    }

    const type = payload?.type ?? '';
    const data = (payload?.data ?? {}) as Record<string, any>;
    const metadata = (data?.metadata ?? {}) as Record<string, unknown>;
    const reference =
      typeof metadata.reference === 'string' ? metadata.reference : undefined;

    switch (type) {
      case 'order.paid':
        return this.applyStatus(
          {
            linkId: typeof data.checkout_id === 'string' ? data.checkout_id : undefined,
            reference,
          },
          PaymentStatus.APPROVED,
          { transactionId: data.id, method: 'card' },
        );
      case 'order.refunded':
        return this.applyStatus(
          {
            transactionId: typeof data.id === 'string' ? data.id : undefined,
            reference,
          },
          PaymentStatus.VOIDED,
          {},
        );
      case 'refund.created':
      case 'refund.updated':
        return this.applyStatus(
          {
            transactionId:
              typeof data.order_id === 'string' ? data.order_id : undefined,
          },
          data.status === 'succeeded'
            ? PaymentStatus.VOIDED
            : PaymentStatus.REFUND_REQUESTED,
          {},
        );
      case 'checkout.updated':
      case 'checkout.expired': {
        const checkoutStatus = String(data.status ?? '');
        const mapped =
          checkoutStatus === 'succeeded'
            ? PaymentStatus.APPROVED
            : checkoutStatus === 'failed' || checkoutStatus === 'expired'
              ? PaymentStatus.DECLINED
              : null;
        if (!mapped) {
          return { received: true, ignored: `checkout ${checkoutStatus}` };
        }
        return this.applyStatus(
          {
            linkId: typeof data.id === 'string' ? data.id : undefined,
            reference,
          },
          mapped,
          {},
        );
      }
      default:
        return { received: true, ignored: `evento no manejado: ${type}` };
    }
  }

  /** Localiza el pago (por checkout, orden o referencia) y avanza su estado. */
  private async applyStatus(
    keys: { linkId?: string; reference?: string; transactionId?: string },
    status: PaymentStatus,
    patch: { transactionId?: unknown; method?: string },
  ) {
    const matchers: Prisma.PaymentWhereInput[] = [];
    if (keys.linkId) matchers.push({ linkId: keys.linkId });
    if (keys.transactionId) matchers.push({ transactionId: keys.transactionId });
    if (keys.reference) matchers.push({ reference: keys.reference });
    if (matchers.length === 0) {
      return { received: true, ignored: 'evento sin claves de correlación' };
    }
    const payment = await this.prisma.payment.findFirst({
      where: { OR: matchers },
      orderBy: { createdAt: 'desc' },
    });
    if (!payment) {
      return { received: true, ignored: 'pago no encontrado' };
    }
    if (STATUS_RANK[status] < STATUS_RANK[payment.status]) {
      return { received: true, ignored: 'estado ya avanzado' };
    }

    await this.prisma.payment.update({
      where: { id: payment.id },
      data: {
        status,
        transactionId:
          typeof patch.transactionId === 'string'
            ? patch.transactionId
            : payment.transactionId,
        method: patch.method ?? payment.method,
        updatedAt: new Date(),
      },
    });
    this.logger.log(`pago ${payment.reference} → ${status}`);
    return { received: true };
  }

  /**
   * Standard Webhooks: `webhook-signature` = "v1,<base64(HMAC-SHA256)>" sobre
   * `${webhook-id}.${webhook-timestamp}.${rawBody}`. El secreto del dashboard
   * puede venir en crudo o codificado base64 (con o sin prefijo whsec_): se
   * prueban ambas interpretaciones.
   */
  private verifySignature(
    rawBody: Buffer | undefined,
    headers: Record<string, string | string[] | undefined>,
  ): boolean {
    const secret = process.env.POLAR_WEBHOOK_SECRET ?? '';
    if (!secret) {
      // Modo demo sin secreto configurado: se acepta, pero queda avisado.
      this.logger.warn(
        'POLAR_WEBHOOK_SECRET no configurado: webhook aceptado sin verificar',
      );
      return true;
    }
    const first = (v: string | string[] | undefined) =>
      Array.isArray(v) ? v[0] : v;
    const id = first(headers['webhook-id']);
    const timestamp = first(headers['webhook-timestamp']);
    const signatureHeader = first(headers['webhook-signature']);
    if (!rawBody || !id || !timestamp || !signatureHeader) return false;

    const signedContent = `${id}.${timestamp}.${rawBody.toString('utf8')}`;
    const stripped = secret.replace(/^(whsec_|polar_whs_)/, '');
    const keys = [Buffer.from(secret, 'utf8'), Buffer.from(stripped, 'base64')];
    const expected = keys.map((key) =>
      createHmac('sha256', key).update(signedContent).digest('base64'),
    );
    const provided = signatureHeader
      .split(' ')
      .map((part) => part.split(',').pop() ?? '')
      .filter((sig) => sig.length > 0);
    return provided.some((sig) =>
      expected.some((exp) => {
        const a = Buffer.from(sig);
        const b = Buffer.from(exp);
        return a.length === b.length && timingSafeEqual(a, b);
      }),
    );
  }
}
