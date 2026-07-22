import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateLeadEventDto,
  QueryLeadEventsDto,
  UpdateLeadEventDto,
} from './lead-events.dto';

@Injectable()
export class LeadEventsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateLeadEventDto) {
    return this.prisma.leadEvent.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryLeadEventsDto) {
    const where = {
      ...(query.leadId && { leadId: query.leadId }),
      ...(query.agentId && { agentId: query.agentId }),
      ...(query.eventType && { eventType: query.eventType }),
    };
    const [data, total] = await Promise.all([
      this.prisma.leadEvent.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.leadEvent.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.leadEvent.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateLeadEventDto) {
    return this.prisma.leadEvent.update({
      where: { id },
      data: this.toData(dto),
    });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.leadEvent.delete({ where: { id } });
  }

  private toData(dto: CreateLeadEventDto): Prisma.LeadEventUncheckedCreateInput;
  private toData(dto: UpdateLeadEventDto): Prisma.LeadEventUncheckedUpdateInput;
  private toData(dto: CreateLeadEventDto | UpdateLeadEventDto): unknown {
    const { payload, ...rest } = dto;
    return {
      ...rest,
      ...(payload !== undefined && {
        payload: payload as Prisma.InputJsonValue,
      }),
    };
  }
}
