import { BadRequestException, Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateAiCallDto,
  QueryAiCallsDto,
  UpdateAiCallDto,
} from './ai-calls.dto';

const aiCallSelect = {
  id: true,
  customerId: true,
  status: true,
  startedAt: true,
  endedAt: true,
  durationSec: true,
  recordingUrl: true,
  summary: true,
  intent: true,
  intentScore: true,
  sentiment: true,
  metadata: true,
  createdAt: true,
} satisfies Prisma.AiCallSelect;

@Injectable()
export class AiCallsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateAiCallDto) {
    if (dto.endedAt) {
      this.assertDateRange(
        new Date(dto.startedAt ?? Date.now()),
        new Date(dto.endedAt),
      );
    }
    return this.prisma.aiCall.create({
      data: this.toData(dto),
      select: aiCallSelect,
    });
  }

  async findAll(query: QueryAiCallsDto) {
    const where = {
      ...(query.customerId && { customerId: query.customerId }),
      ...(query.status && { status: query.status }),
      ...(query.intent && { intent: query.intent }),
      ...((query.from || query.to) && {
        startedAt: {
          ...(query.from && { gte: new Date(query.from) }),
          ...(query.to && { lte: new Date(query.to) }),
        },
      }),
    };
    const [data, total] = await Promise.all([
      this.prisma.aiCall.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { startedAt: query.order },
        select: aiCallSelect,
      }),
      this.prisma.aiCall.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.aiCall.findUniqueOrThrow({
      where: { id },
      select: aiCallSelect,
    });
  }

  async update(id: string, dto: UpdateAiCallDto) {
    const current = await this.prisma.aiCall.findUnique({ where: { id } });
    if (current && (dto.startedAt || dto.endedAt)) {
      const startedAt = dto.startedAt
        ? new Date(dto.startedAt)
        : current.startedAt;
      const endedAt = dto.endedAt ? new Date(dto.endedAt) : current.endedAt;
      if (endedAt) this.assertDateRange(startedAt, endedAt);
    }
    return this.prisma.aiCall.update({
      where: { id },
      data: this.toData(dto),
      select: aiCallSelect,
    });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.aiCall.delete({ where: { id } });
  }

  private toData(dto: CreateAiCallDto): Prisma.AiCallUncheckedCreateInput;
  private toData(dto: UpdateAiCallDto): Prisma.AiCallUncheckedUpdateInput;
  private toData(dto: CreateAiCallDto | UpdateAiCallDto): unknown {
    const { startedAt, endedAt, intentScore, metadata, ...rest } = dto;
    return {
      ...rest,
      ...(startedAt !== undefined && { startedAt: new Date(startedAt) }),
      ...(endedAt !== undefined && { endedAt: new Date(endedAt) }),
      ...(intentScore !== undefined && {
        intentScore: new Prisma.Decimal(intentScore),
      }),
      ...(metadata !== undefined && {
        metadata: metadata as Prisma.InputJsonValue,
      }),
    };
  }

  private assertDateRange(startedAt: Date, endedAt: Date): void {
    if (endedAt < startedAt)
      throw new BadRequestException(
        'endedAt no puede ser anterior a startedAt',
      );
  }
}
