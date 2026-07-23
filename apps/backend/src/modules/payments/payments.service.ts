import { createHash } from 'crypto';
import { Injectable, Logger, NotFoundException } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { PaymentStatus } from '../../generated/prisma/enums';
import { PrismaService } from '../../prisma/prisma.service';
import { CreatePaymentDto, UpdatePaymentDto } from './payments.dto';

/**
 * Sistema de registro de pagos del cierre autónomo (Wompi sandbox o demo).
 *
 * El servicio IA crea el pago al generar el link (pending) y lo consulta antes
 * de emitir la póliza. El estado lo actualizan dos caminos que convergen aquí:
 * el webhook `transaction.updated` de Wompi (fuente primaria, firmado con
 * WOMPI_EVENTS_SECRET) y el polling de `verificar_pago` cuando el webhook no
 * alcanza a llegar (p. ej. entorno local sin URL pública).
 */

/** Evento de Wompi (estructura documentada en docs.wompi.co/docs/colombia/eventos). */
type WompiEvent = {
  event?: string;
  data?: { transaction?: WompiTransaction } & Record<string, unknown>;
  timestamp?: number;
  signature?: { properties?: string[]; checksum?: string };
};

type WompiTransaction = {
  id?: string;
  status?: string;
  reference?: string;
  payment_link_id?: string;
  payment_method_type?: string;
  amount_in_cents?: number;
} & Record<string, unknown>;

const WOMPI_STATUS_MAP: Record<string, PaymentStatus> = {
  PENDING: PaymentStatus.PENDING,
  APPROVED: PaymentStatus.APPROVED,
  DECLINED: PaymentStatus.DECLINED,
  VOIDED: PaymentStatus.VOIDED,
  ERROR: PaymentStatus.ERROR,
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
        provider: dto.provider ?? 'wompi',
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
   * Webhook de Wompi. Siempre responde 200 (aunque el evento se ignore) para
   * no disparar los reintentos de la pasarela; la autenticidad se valida con
   * el checksum SHA256 (propiedades firmadas + timestamp + secreto de eventos).
   */
  async handleWebhook(event: WompiEvent) {
    if (event?.event !== 'transaction.updated') {
      return { received: true, ignored: 'evento no manejado' };
    }
    if (!this.verifySignature(event)) {
      this.logger.warn('webhook de Wompi con firma inválida: ignorado');
      return { received: true, ignored: 'firma inválida' };
    }

    const tx = event.data?.transaction ?? {};
    const status = WOMPI_STATUS_MAP[(tx.status ?? '').toUpperCase()];
    if (!status) {
      return { received: true, ignored: `estado desconocido: ${tx.status}` };
    }

    const matchers: Prisma.PaymentWhereInput[] = [];
    if (tx.payment_link_id) matchers.push({ linkId: tx.payment_link_id });
    if (tx.reference) matchers.push({ reference: tx.reference });
    if (matchers.length === 0) {
      return { received: true, ignored: 'transacción sin link ni referencia' };
    }
    const payment = await this.prisma.payment.findFirst({
      where: { OR: matchers },
      orderBy: { createdAt: 'desc' },
    });
    if (!payment) {
      return { received: true, ignored: 'pago no encontrado' };
    }
    // Un estado final (aprobado/anulado) no retrocede a pending por un
    // webhook rezagado que llegue fuera de orden.
    if (
      status === PaymentStatus.PENDING &&
      payment.status !== PaymentStatus.PENDING
    ) {
      return { received: true, ignored: 'estado ya avanzado' };
    }

    await this.prisma.payment.update({
      where: { id: payment.id },
      data: {
        status,
        transactionId: tx.id ?? payment.transactionId,
        method: tx.payment_method_type ?? payment.method,
        updatedAt: new Date(),
      },
    });
    this.logger.log(
      `pago ${payment.reference} → ${status} (tx ${tx.id ?? 'n/a'})`,
    );
    return { received: true };
  }

  private verifySignature(event: WompiEvent): boolean {
    const secret = process.env.WOMPI_EVENTS_SECRET ?? '';
    if (!secret) {
      // Modo demo sin secreto configurado: se acepta, pero queda avisado.
      this.logger.warn(
        'WOMPI_EVENTS_SECRET no configurado: webhook aceptado sin verificar',
      );
      return true;
    }
    const props = event?.signature?.properties ?? [];
    const data = (event?.data ?? {}) as Record<string, unknown>;
    const concatenated = props
      .map((path) =>
        String(
          path
            .split('.')
            .reduce<unknown>(
              (acc, key) => (acc as Record<string, unknown> | undefined)?.[key],
              data,
            ) ?? '',
        ),
      )
      .join('');
    const checksum = createHash('sha256')
      .update(`${concatenated}${event?.timestamp ?? ''}${secret}`)
      .digest('hex');
    return (
      checksum === String(event?.signature?.checksum ?? '').toLowerCase()
    );
  }
}
