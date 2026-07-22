import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateAlertDto, QueryAlertsDto, UpdateAlertDto } from './alerts.dto';

@Injectable()
export class AlertsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateAlertDto) {
    return this.prisma.alert.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryAlertsDto) {
    const where = {
      ...(query.teamId && { teamId: query.teamId }),
      ...(query.leadId && { leadId: query.leadId }),
      ...(query.agentId && { agentId: query.agentId }),
      ...(query.resolved !== undefined && { resolved: query.resolved }),
      ...(query.severity && { severity: query.severity }),
    };
    const [data, total] = await Promise.all([
      this.prisma.alert.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.alert.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.alert.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateAlertDto) {
    return this.prisma.alert.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.alert.delete({ where: { id } });
  }

  private toData(dto: CreateAlertDto): Prisma.AlertUncheckedCreateInput;
  private toData(dto: UpdateAlertDto): Prisma.AlertUncheckedUpdateInput;
  private toData(dto: CreateAlertDto | UpdateAlertDto): unknown {
    const resolvedAt =
      dto.resolved === false
        ? null
        : dto.resolvedAt
          ? new Date(dto.resolvedAt)
          : dto.resolved === true
            ? new Date()
            : undefined;

    return {
      ...dto,
      ...(resolvedAt !== undefined && { resolvedAt }),
    };
  }
}
