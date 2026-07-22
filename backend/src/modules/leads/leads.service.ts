import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateLeadDto, QueryLeadsDto, UpdateLeadDto } from './leads.dto';

@Injectable()
export class LeadsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateLeadDto) {
    return this.prisma.lead.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryLeadsDto) {
    const where = {
      ...(query.customerId && { customerId: query.customerId }),
      ...(query.agentId && { agentId: query.agentId }),
      ...(query.insuranceType && { insuranceType: query.insuranceType }),
      ...(query.status && { status: query.status }),
      ...(query.intent && { intent: query.intent }),
    };
    const [data, total] = await Promise.all([
      this.prisma.lead.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.lead.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.lead.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateLeadDto) {
    return this.prisma.lead.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.lead.delete({ where: { id } });
  }

  private toData(dto: CreateLeadDto): Prisma.LeadUncheckedCreateInput;
  private toData(dto: UpdateLeadDto): Prisma.LeadUncheckedUpdateInput;
  private toData(dto: CreateLeadDto | UpdateLeadDto): unknown {
    const { assignedAt, firstContactAt, closedAt, aiNextSteps, ...rest } = dto;
    return {
      ...rest,
      ...(assignedAt !== undefined && { assignedAt: new Date(assignedAt) }),
      ...(firstContactAt !== undefined && {
        firstContactAt: new Date(firstContactAt),
      }),
      ...(closedAt !== undefined && { closedAt: new Date(closedAt) }),
      ...(aiNextSteps !== undefined && {
        aiNextSteps: aiNextSteps as Prisma.InputJsonValue,
      }),
    };
  }
}
