import { Injectable } from '@nestjs/common';
import { Channel, LeadStatus } from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CustomersService } from '../customers/customers.service';
import { higherChannel } from './channel-rank';
import {
  CreateLeadDto,
  QueryLeadsDto,
  QueryLeadsQueueDto,
  UpdateLeadDto,
  UpsertLeadDto,
} from './leads.dto';

const OPEN_STATUSES: LeadStatus[] = [
  LeadStatus.NUEVO,
  LeadStatus.CONTACTADO,
  LeadStatus.COTIZADO,
  LeadStatus.NEGOCIACION,
];

@Injectable()
export class LeadsService {
  constructor(
    private readonly prisma: PrismaService,
    private readonly customers: CustomersService,
  ) {}

  /**
   * Cola priorizada (`GET /leads/queue`). Sin `agentId` = vista de manager
   * (todo el equipo); con `agentId` = la cola de ese agente puntual. Orden:
   * mayor `priorityScore` primero; a igual score, quien lleva más tiempo
   * esperando respuesta.
   */
  async findQueue(tenantId: string, query: QueryLeadsQueueDto) {
    const where = {
      teamId: tenantId,
      status: { in: OPEN_STATUSES },
      ...(query.agentId && { agentId: query.agentId }),
    };
    const [data, total] = await Promise.all([
      this.prisma.lead.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: [
          { priorityScore: 'desc' },
          { lastCustomerResponseAt: { sort: 'asc', nulls: 'first' } },
          { createdAt: 'asc' },
        ],
      }),
      this.prisma.lead.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  /**
   * Resuelve/crea el Lead de un teléfono (lo usa el servicio IA en Python,
   * que solo conoce el teléfono, no un customerId). Canal por defecto
   * WHATSAPP: es el canal primario que sirve hoy el cotizador de Python.
   */
  async upsertByPhone(tenantId: string, dto: UpsertLeadDto) {
    const customer = await this.customers.findOrCreateByPhone(
      tenantId,
      dto.phone,
    );
    const lead = await this.findOrCreateOpenLead(
      tenantId,
      customer.id,
      Channel.WHATSAPP,
    );
    if (!dto.insuranceType && !dto.status) return lead;
    return this.prisma.lead.update({
      where: { id: lead.id },
      data: {
        ...(dto.insuranceType && { insuranceType: dto.insuranceType }),
        ...(dto.status && { status: dto.status }),
      },
    });
  }

  create(tenantId: string, dto: CreateLeadDto) {
    return this.prisma.lead.create({
      data: { ...this.toData(dto), teamId: tenantId },
    });
  }

  /**
   * Punto de entrada del "primer contacto real": lo llaman
   * `AiCallsService.openSession` (WhatsApp/web chat) y
   * `ElevenLabsService.handlePostCallWebhook` (llamada) justo después de
   * resolver/crear el Customer. Si el customer ya tiene un Lead abierto
   * (`status` no cerrado), lo reutiliza y solo hace avanzar
   * `highestChannel` (ratchet, nunca retrocede); si no, crea uno nuevo con
   * `firstChannel = highestChannel = channel`.
   */
  async findOrCreateOpenLead(
    tenantId: string,
    customerId: string,
    channel: Channel,
  ) {
    const existing = await this.prisma.lead.findFirst({
      where: { teamId: tenantId, customerId, status: { in: OPEN_STATUSES } },
      orderBy: { createdAt: 'desc' },
    });

    if (existing) {
      const nextHighest = higherChannel(existing.highestChannel, channel);
      if (nextHighest === existing.highestChannel) return existing;
      return this.prisma.lead.update({
        where: { id: existing.id },
        data: { highestChannel: nextHighest },
      });
    }

    return this.prisma.lead.create({
      data: {
        teamId: tenantId,
        customerId,
        firstChannel: channel,
        highestChannel: channel,
      },
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
    const data = this.toData(dto);
    // Un intent puesto a mano por un agente pausa el motor de scoring sobre
    // ese campo hasta que expire (ver LEAD_SCORE_OVERRIDE_DAYS) — si no, el
    // próximo barrido del cron lo pisaría en minutos.
    if (dto.intent !== undefined) {
      data.intentOverride = dto.intent;
      data.intentOverrideAt = new Date();
    }
    return this.prisma.lead.update({ where: { id }, data });
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
