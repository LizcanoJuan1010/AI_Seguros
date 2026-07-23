import { BadRequestException, Injectable } from '@nestjs/common';
import { CallStatus } from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CustomersService } from '../customers/customers.service';
import {
  CreateAiCallDto,
  OpenSessionDto,
  QueryAiCallsDto,
  UpdateAiCallDto,
} from './ai-calls.dto';

// Ventana de inactividad para considerar que un canal "sin llamada" (WhatsApp,
// web chat) sigue siendo la MISMA sesión. Pasado este tiempo sin mensajes,
// openSession() cierra la sesión vieja y abre una nueva.
const SESSION_IDLE_MINUTES = 30;

const aiCallSelect = {
  id: true,
  teamId: true,
  customerId: true,
  channel: true,
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
  constructor(
    private readonly prisma: PrismaService,
    private readonly customers: CustomersService,
  ) {}

  /**
   * Punto de entrada para canales sin límite de llamada explícito (WhatsApp,
   * web chat): resuelve/crea el Customer por teléfono y reutiliza la AiCall
   * EN_CURSO más reciente de ese (customer, channel) si tuvo actividad hace
   * menos de `SESSION_IDLE_MINUTES`; si no, la cierra y abre una nueva. Así
   * el servicio IA (Python) no decide la regla de sesión, solo la consume.
   */
  async openSession(tenantId: string, dto: OpenSessionDto) {
    const customer = await this.customers.findOrCreateByPhone(
      tenantId,
      dto.phone,
    );
    const cutoff = new Date(Date.now() - SESSION_IDLE_MINUTES * 60_000);

    const openCall = await this.prisma.aiCall.findFirst({
      where: {
        teamId: tenantId,
        customerId: customer.id,
        channel: dto.channel,
        status: CallStatus.EN_CURSO,
      },
      orderBy: { startedAt: 'desc' },
      include: { messages: { orderBy: { spokenAt: 'desc' }, take: 1 } },
    });

    if (openCall) {
      const lastActivity = openCall.messages[0]?.spokenAt ?? openCall.startedAt;
      if (lastActivity >= cutoff) {
        return { id: openCall.id, customerId: customer.id };
      }
      await this.prisma.aiCall.update({
        where: { id: openCall.id },
        data: { status: CallStatus.COMPLETADA, endedAt: new Date() },
      });
    }

    const created = await this.prisma.aiCall.create({
      data: {
        teamId: tenantId,
        customerId: customer.id,
        channel: dto.channel,
        status: CallStatus.EN_CURSO,
      },
    });
    return { id: created.id, customerId: customer.id };
  }

  create(tenantId: string, dto: CreateAiCallDto) {
    if (dto.endedAt) {
      this.assertDateRange(
        new Date(dto.startedAt ?? Date.now()),
        new Date(dto.endedAt),
      );
    }
    return this.prisma.aiCall.create({
      data: { ...this.toData(dto), teamId: tenantId },
      select: aiCallSelect,
    });
  }

  async findAll(tenantId: string, query: QueryAiCallsDto) {
    const where = {
      teamId: tenantId,
      ...(query.customerId && { customerId: query.customerId }),
      ...(query.channel && { channel: query.channel }),
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

  findOne(tenantId: string, id: string) {
    return this.prisma.aiCall.findFirstOrThrow({
      where: { id, teamId: tenantId },
      select: aiCallSelect,
    });
  }

  async update(tenantId: string, id: string, dto: UpdateAiCallDto) {
    const current = await this.findOne(tenantId, id);
    if (dto.startedAt || dto.endedAt) {
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

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
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
