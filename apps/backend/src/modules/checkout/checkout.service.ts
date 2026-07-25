import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import {
  LeadIntent,
  LeadStatus,
  PolicyStatus,
  QuoteStatus,
} from '../../generated/prisma/enums';
import { PrismaService } from '../../prisma/prisma.service';
import { CheckoutDto } from './checkout.dto';

const DEFAULT_DOCUMENT_TYPE = 'CC';
const QUOTE_VALID_DAYS = 30;

@Injectable()
export class CheckoutService {
  constructor(private readonly prisma: PrismaService) {}

  async checkout(tenantId: string, dto: CheckoutDto) {
    if (dto.consentData !== true) {
      throw new BadRequestException(
        'Se requiere consentimiento de datos (habeas data)',
      );
    }

    const now = new Date();
    const documentType = dto.customer.documentType ?? DEFAULT_DOCUMENT_TYPE;
    const premium = new Prisma.Decimal(dto.monthlyPremiumCop);

    const endDate = new Date(now);
    endDate.setFullYear(endDate.getFullYear() + 1);

    const validUntil = new Date(now);
    validUntil.setDate(validUntil.getDate() + QUOTE_VALID_DAYS);

    const birthDate = dto.customer.birthDate
      ? new Date(dto.customer.birthDate)
      : undefined;

    // The schema has no Payment entity, so the (simulated) payment reference
    // is persisted inside the Quote.coverage JSON under a `payment` key.
    const coverage: Prisma.InputJsonValue = {
      ...(dto.coverage ?? {}),
      ...(dto.payment ? { payment: { ...dto.payment } } : {}),
    };

    return this.prisma.$transaction(async (tx) => {
      // a) Upsert Customer by (documentType, documentId); register consent.
      const customer = await tx.customer.upsert({
        where: {
          documentType_documentId: {
            documentType,
            documentId: dto.customer.documentId,
          },
        },
        create: {
          teamId: tenantId,
          fullName: dto.customer.fullName,
          documentType,
          documentId: dto.customer.documentId,
          email: dto.customer.email,
          phone: dto.customer.phone,
          city: dto.customer.city,
          department: dto.customer.department,
          birthDate,
          consentData: true,
          consentAt: now,
        },
        update: {
          fullName: dto.customer.fullName,
          email: dto.customer.email,
          phone: dto.customer.phone,
          city: dto.customer.city,
          department: dto.customer.department,
          birthDate,
          consentData: true,
          consentAt: now,
          updatedAt: now,
        },
      });

      // b) Map insuranceType -> seeded product (first active one).
      const product = await tx.product.findFirst({
        where: { insuranceType: dto.insuranceType, isActive: true },
        orderBy: { createdAt: 'asc' },
      });
      if (!product) {
        throw new NotFoundException(
          `No hay un producto activo para el tipo ${dto.insuranceType}`,
        );
      }

      // c) Create the closed-won Lead. agentId is nullable in the schema, so
      // an autonomous (no-human) close leaves it null.
      const lead = await tx.lead.create({
        data: {
          teamId: tenantId,
          customerId: customer.id,
          insuranceType: dto.insuranceType,
          status: LeadStatus.CERRADO_GANADO,
          intent: LeadIntent.CALIENTE,
          firstContactAt: now,
          closedAt: now,
        },
      });

      // d) Create the accepted Quote.
      const quote = await tx.quote.create({
        data: {
          teamId: tenantId,
          leadId: lead.id,
          productId: product.id,
          coverage,
          monthlyPremiumCop: premium,
          status: QuoteStatus.ACEPTADA,
          validUntil,
        },
      });

      // e) Create the Policy with a generated, unique policy number.
      const policyNumber = await this.nextPolicyNumber(tx, now.getFullYear());
      const policy = await tx.policy.create({
        data: {
          teamId: tenantId,
          quoteId: quote.id,
          customerId: customer.id,
          insurerId: product.insurerId,
          policyNumber,
          status: PolicyStatus.VIGENTE,
          startDate: now,
          endDate,
          monthlyPremiumCop: premium,
        },
      });

      return {
        policyNumber: policy.policyNumber,
        policyId: policy.id,
        customerId: customer.id,
        status: policy.status,
        startDate: policy.startDate,
        endDate: policy.endDate,
        insuranceType: dto.insuranceType,
        monthlyPremiumCop: policy.monthlyPremiumCop,
      };
    });
  }

  // POL-YYYY-000NNN, sequenced off the current policy count and guarded
  // against collisions (e.g. deleted rows) inside the transaction.
  private async nextPolicyNumber(
    tx: Prisma.TransactionClient,
    year: number,
  ): Promise<string> {
    const format = (seq: number) =>
      `POL-${year}-${String(seq).padStart(6, '0')}`;
    let seq = (await tx.policy.count()) + 1;
    let candidate = format(seq);
    while (await tx.policy.findUnique({ where: { policyNumber: candidate } })) {
      seq += 1;
      candidate = format(seq);
    }
    return candidate;
  }
}
