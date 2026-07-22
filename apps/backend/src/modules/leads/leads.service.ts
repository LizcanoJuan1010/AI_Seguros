import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateLeadDto, QueryLeadsDto, UpdateLeadDto } from './leads.dto';

@Injectable()
export class LeadsService {
  constructor(private readonly prisma: PrismaService) {}

  create(tenantId: string, dto: CreateLeadDto) {
    return this.prisma.lead.create({
      data: { ...this.toData(dto), teamId: tenantId },
    });
  }

  async findAll(tenantId: string, query: QueryLeadsDto) {
    const where = {
      teamId: tenantId,
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

  findOne(tenantId: string, id: string) {
    return this.prisma.lead.findFirstOrThrow({
      where: { id, teamId: tenantId },
    });
  }

  async update(tenantId: string, id: string, dto: UpdateLeadDto) {
    await this.findOne(tenantId, id);
    return this.prisma.lead.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
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
