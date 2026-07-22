import { BadRequestException, Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreatePolicyDto,
  QueryPoliciesDto,
  UpdatePolicyDto,
} from './policies.dto';

@Injectable()
export class PoliciesService {
  constructor(private readonly prisma: PrismaService) {}

  create(tenantId: string, dto: CreatePolicyDto) {
    this.assertDateRange(new Date(dto.startDate), new Date(dto.endDate));
    return this.prisma.policy.create({
      data: { ...this.toData(dto), teamId: tenantId },
    });
  }

  async findAll(tenantId: string, query: QueryPoliciesDto) {
    const where = {
      teamId: tenantId,
      ...(query.customerId && { customerId: query.customerId }),
      ...(query.agentId && { agentId: query.agentId }),
      ...(query.status && { status: query.status }),
    };
    const [data, total] = await Promise.all([
      this.prisma.policy.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.policy.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(tenantId: string, id: string) {
    return this.prisma.policy.findFirstOrThrow({
      where: { id, teamId: tenantId },
    });
  }

  async update(tenantId: string, id: string, dto: UpdatePolicyDto) {
    // findFirstOrThrow garantiza que la póliza pertenece al tenant antes de
    // permitir el update; una póliza de otro tenant lanza NotFound.
    const current = await this.prisma.policy.findFirstOrThrow({
      where: { id, teamId: tenantId },
    });
    this.assertDateRange(
      dto.startDate ? new Date(dto.startDate) : current.startDate,
      dto.endDate ? new Date(dto.endDate) : current.endDate,
    );
    return this.prisma.policy.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
    await this.prisma.policy.delete({ where: { id } });
  }

  private toData(dto: CreatePolicyDto): Prisma.PolicyUncheckedCreateInput;
  private toData(dto: UpdatePolicyDto): Prisma.PolicyUncheckedUpdateInput;
  private toData(dto: CreatePolicyDto | UpdatePolicyDto): unknown {
    const { startDate, endDate, monthlyPremiumCop, ...rest } = dto;
    return {
      ...rest,
      ...(startDate !== undefined && { startDate: new Date(startDate) }),
      ...(endDate !== undefined && { endDate: new Date(endDate) }),
      ...(monthlyPremiumCop !== undefined && {
        monthlyPremiumCop: new Prisma.Decimal(monthlyPremiumCop),
      }),
    };
  }

  private assertDateRange(startDate: Date, endDate: Date): void {
    if (endDate <= startDate)
      throw new BadRequestException('endDate debe ser posterior a startDate');
  }
}
