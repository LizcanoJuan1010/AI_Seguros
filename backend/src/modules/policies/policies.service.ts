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

  create(dto: CreatePolicyDto) {
    this.assertDateRange(new Date(dto.startDate), new Date(dto.endDate));
    return this.prisma.policy.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryPoliciesDto) {
    const where = {
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

  findOne(id: string) {
    return this.prisma.policy.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdatePolicyDto) {
    const current = await this.prisma.policy.findUnique({ where: { id } });
    if (current) {
      this.assertDateRange(
        dto.startDate ? new Date(dto.startDate) : current.startDate,
        dto.endDate ? new Date(dto.endDate) : current.endDate,
      );
    }
    return this.prisma.policy.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
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
