import { createHmac, randomBytes, timingSafeEqual } from 'crypto';
import {
  BadRequestException,
  Injectable,
  Logger,
  NotFoundException,
  UnauthorizedException,
} from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { PaymentStatus } from '../../generated/prisma/enums';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateCheckoutDto,
  CreatePaymentDto,
  UpdatePaymentDto,
} from './payments.dto';
import { PolarClient } from './polar.client';

/**
 * Sistema de registro de pagos del cierre autónomo (Polar sandbox o demo).
 *
 * Nest es el único dueño de Polar HTTP (create checkout + webhook). El servicio
 * IA llama `POST /payments/checkout` y consulta estado vía GET/PATCH. El estado
 * lo actualizan: webhooks Polar (HMAC fail-closed fuera de demo) y el agente
 * vía PATCH (p.ej. auto-APPROVE en modo demo).
 *
 * Correlación: `linkId` = checkout_id Polar, `transactionId` = order id,
 * `reference` = SEG-... en metadata. Nunca se confía en teamId del body Polar.
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

  constructor(
    private readonly prisma: PrismaService,
    private readonly polar: PolarClient,
  ) {}

  /** Modo demo: sin POLAR_ACCESS_TOKEN no hay HTTP a Polar. */
  isDemoMode(): boolean {
    return !this.polar.isConfigured();
  }

  /**
   * Crea checkout Polar (o demo) y persiste Payment con teamId + checkoutUrl.
   * → `{reference, checkoutUrl, linkId, provider, status, amountCop, concept, demo}`
   */
  async createCheckout(tenantId: string, dto: CreateCheckoutDto) {
    if (!tenantId?.trim()) {
      throw new BadRequestException('tenant requerido');
    }
    const amount = Number(dto.amountCop);
    if (!Number.isFinite(amount) || amount <= 0) {
      throw new BadRequestException('amountCop debe ser un número positivo');
    }
    const concept =
      (dto.concept || '').trim() || 'Primera mensualidad — Seguro Tequendama';
    const reference = `SEG-${randomBytes(5).toString('hex').toUpperCase()}`;

    let linkId: string;
    let checkoutUrl: string | null;
    let provider: string;
    let demo: boolean;

    if (this.isDemoMode()) {
      linkId = `demo-${reference}`;
      checkoutUrl = null;
      provider = 'demo';
      demo = true;
    } else {
      try {
        const created = await this.polar.createCheckout(
          amount,
          concept,
          reference,
        );
        linkId = created.checkoutId;
        checkoutUrl = created.checkoutUrl;
        provider = 'polar';
        demo = false;
      } catch (err) {
        this.logger.error(
          `Polar createCheckout falló: ${(err as Error).message}`,
        );
        throw new BadRequestException(
          `la pasarela no pudo crear el link de pago: ${(err as Error).message}`,
        );
      }
    }

    const payment = await this.create(tenantId, {
      reference,
      provider,
      linkId,
      checkoutUrl: checkoutUrl ?? undefined,
      amountCop: amount,
      concept,
      sessionKey: dto.sessionKey,
    });

    return {
      reference: payment.reference,
      checkoutUrl: payment.checkoutUrl,
      linkId: payment.linkId,
      provider: payment.provider,
      status: payment.status,
      amountCop: Number(payment.amountCop),
      concept: payment.concept,
      demo,
    };
  }

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
    // Los null del polling (p.ej. transactionId aún desconocido) no deben
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
   * Webhook de Polar.
   * - Non-demo (POLAR_ACCESS_TOKEN set): exige POLAR_WEBHOOK_SECRET y firma
   *   válida; rechaza con 401 (fail-closed).
   * - Demo (sin token): puede aceptar sin secreto (política documentada).
   * Responde 200 en eventos válidos/ignorados para cortar reintentos.
   */
  async handleWebhook(
    rawBody: Buffer | undefined,
    headers: Record<string, string | string[] | undefined>,
    payload: PolarWebhookPayload,
  ) {
    if (!this.isDemoMode()) {
      const secret = process.env.POLAR_WEBHOOK_SECRET?.trim() ?? '';
      if (!secret || !this.verifySignature(rawBody, headers, secret)) {
        this.logger.warn(
          'webhook de Polar rechazado (fail-closed: secreto/firma inválidos)',
        );
        throw new UnauthorizedException(
          'Firma de webhook inválida o secreto no configurado',
        );
      }
    } else {
      const secret = process.env.POLAR_WEBHOOK_SECRET?.trim() ?? '';
      if (secret && !this.verifySignature(rawBody, headers, secret)) {
        this.logger.warn('webhook demo con firma inválida: ignorado');
        return { received: true, ignored: 'firma inválida' };
      }
      if (!secret) {
        this.logger.warn(
          'POLAR_WEBHOOK_SECRET no configurado (demo): webhook aceptado sin verificar',
        );
      }
    }

    const type = payload?.type ?? '';
    const data = (payload?.data ?? {}) as Record<string, any>;
    const metadata = (data?.metadata ?? {}) as Record<string, unknown>;
    const reference =
      typeof metadata.reference === 'string' ? metadata.reference : undefined;
    // Nunca usar teamId / tenant del body Polar — solo reference|linkId|tx.

    switch (type) {
      case 'order.paid':
        return this.applyStatus(
          {
            linkId:
              typeof data.checkout_id === 'string' ? data.checkout_id : undefined,
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
      // No reasignar teamId desde el webhook — solo status / tx / method.
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
   * `${webhook-id}.${webhook-timestamp}.${rawBody}`.
   */
  private verifySignature(
    rawBody: Buffer | undefined,
    headers: Record<string, string | string[] | undefined>,
    secret: string,
  ): boolean {
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
