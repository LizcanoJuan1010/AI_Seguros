import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateCallMessageDto,
  QueryCallMessagesDto,
  UpdateCallMessageDto,
} from './call-messages.dto';

@Injectable()
export class CallMessagesService {
  constructor(private readonly prisma: PrismaService) {}

  async create(tenantId: string, dto: CreateCallMessageDto) {
    await this.prisma.aiCall.findFirstOrThrow({
      where: { id: dto.callId, teamId: tenantId },
    });
    return this.prisma.callMessage.create({ data: this.toData(dto) });
  }

  async findAll(tenantId: string, query: QueryCallMessagesDto) {
    const where = {
      call: { teamId: tenantId },
      ...(query.callId && { callId: query.callId }),
      ...(query.speaker && { speaker: query.speaker }),
    };
    const [data, total] = await Promise.all([
      this.prisma.callMessage.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { spokenAt: query.order },
      }),
      this.prisma.callMessage.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(tenantId: string, id: string) {
    return this.prisma.callMessage.findFirstOrThrow({
      where: { id, call: { teamId: tenantId } },
    });
  }

  async update(tenantId: string, id: string, dto: UpdateCallMessageDto) {
    await this.findOne(tenantId, id);
    return this.prisma.callMessage.update({
      where: { id },
      data: this.toData(dto),
    });
  }

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
    await this.prisma.callMessage.delete({ where: { id } });
  }

  private toData(
    dto: CreateCallMessageDto,
  ): Prisma.CallMessageUncheckedCreateInput;
  private toData(
    dto: UpdateCallMessageDto,
  ): Prisma.CallMessageUncheckedUpdateInput;
  private toData(dto: CreateCallMessageDto | UpdateCallMessageDto): unknown {
    return {
      ...dto,
      ...(dto.spokenAt !== undefined && { spokenAt: new Date(dto.spokenAt) }),
    };
  }
}
