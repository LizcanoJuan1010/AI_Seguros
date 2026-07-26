import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateClaimDto, QueryClaimsDto, UpdateClaimDto } from './claims.dto';

@Injectable()
export class ClaimsService {
  constructor(private readonly prisma: PrismaService) {}

  async create(tenantId: string, dto: CreateClaimDto) {
    const claimNumber =
      dto.claimNumber ?? (await this.nextClaimNumber(new Date().getFullYear()));
    return this.prisma.claim.create({
      data: { ...this.toData(dto), claimNumber, teamId: tenantId },
    });
  }

  async findAll(tenantId: string, query: QueryClaimsDto) {
    const where = {
      teamId: tenantId,
      ...(query.policyId && { policyId: query.policyId }),
      ...(query.customerId && { customerId: query.customerId }),
      ...(query.status && { status: query.status }),
    };
    const [data, total] = await Promise.all([
      this.prisma.claim.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
        // El nombre del cliente permite enlazar el reclamo a su expediente 360
        // desde el panel del gerente (pestaña Reclamos).
        include: { customer: { select: { fullName: true } } },
      }),
      this.prisma.claim.count({ where }),
    ]);
    const mapped = data.map(({ customer, ...claim }) => ({
      ...claim,
      customerName: customer?.fullName ?? null,
    }));
    return paginated(mapped, total, query.page, query.limit);
  }

  findOne(tenantId: string, id: string) {
    return this.prisma.claim.findFirstOrThrow({
      where: { id, teamId: tenantId },
    });
  }

  async update(tenantId: string, id: string, dto: UpdateClaimDto) {
    // Garantiza que el reclamo pertenece al tenant antes de permitir el update.
    await this.findOne(tenantId, id);
    return this.prisma.claim.update({
      where: { id },
      data: { ...this.toData(dto), updatedAt: new Date() },
    });
  }

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
    await this.prisma.claim.delete({ where: { id } });
  }

  private toData(dto: CreateClaimDto | UpdateClaimDto) {
    const {
      claimNumber: _claimNumber,
      incidentDate,
      amountEstimateCop,
      fraudScore,
      ...rest
    } = dto;
    return {
      ...rest,
      ...(incidentDate !== undefined && {
        incidentDate: new Date(incidentDate),
      }),
      ...(amountEstimateCop !== undefined && {
        amountEstimateCop: new Prisma.Decimal(amountEstimateCop),
      }),
      ...(fraudScore !== undefined && {
        fraudScore: new Prisma.Decimal(fraudScore),
      }),
    };
  }

  // CLM-YYYY-000NNN, con guardia de colisión (mismo patrón de policies).
  private async nextClaimNumber(year: number): Promise<string> {
    const format = (seq: number) =>
      `CLM-${year}-${String(seq).padStart(6, '0')}`;
    let seq = (await this.prisma.claim.count()) + 1;
    let candidate = format(seq);
    while (
      await this.prisma.claim.findUnique({
        where: { claimNumber: candidate },
      })
    ) {
      seq += 1;
      candidate = format(seq);
    }
    return candidate;
  }
}
