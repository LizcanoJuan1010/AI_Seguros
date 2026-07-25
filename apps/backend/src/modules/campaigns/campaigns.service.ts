import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Cron } from '@nestjs/schedule';
import { LeadStatus } from '../../generated/prisma/enums';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateCampaignDto,
  QueryCampaignsDto,
  SendCampaignDto,
  UpdateCampaignSendDto,
} from './campaigns.dto';

// Duplicada a propósito (mismo valor que leads.service.ts/lead-scoring.service.ts
// — ninguno de los dos la exporta desde un módulo compartido, así que se
// repite acá siguiendo la misma convención ya establecida en el repo).
const OPEN_STATUSES: LeadStatus[] = [
  LeadStatus.NUEVO,
  LeadStatus.CONTACTADO,
  LeadStatus.COTIZADO,
  LeadStatus.NEGOCIACION,
];

const MAX_SEGMENT_SIZE = 300;
const STALE_PENDING_MINUTES = 90;

interface BroadcastSend {
  send_id: string;
  phone: string;
  message: string;
}

@Injectable()
export class CampaignsService {
  private readonly logger = new Logger(CampaignsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly config: ConfigService,
  ) {}

  create(tenantId: string, dto: CreateCampaignDto) {
    return this.prisma.campaign.create({ data: { ...dto, teamId: tenantId } });
  }

  async findAll(tenantId: string, query: QueryCampaignsDto) {
    const where = {
      teamId: tenantId,
      ...(query.channel && { channel: query.channel }),
    };
    const [data, total] = await Promise.all([
      this.prisma.campaign.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.campaign.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(tenantId: string, id: string) {
    return this.prisma.campaign.findFirstOrThrow({ where: { id, teamId: tenantId } });
  }

  async sendsSummary(tenantId: string, id: string) {
    await this.findOne(tenantId, id); // valida pertenencia al tenant
    const rows = await this.prisma.campaignSend.groupBy({
      by: ['status'],
      where: { campaignId: id },
      _count: true,
    });
    return rows.map((r) => ({ status: r.status, count: r._count }));
  }

  /**
   * Resuelve el segmento de leads por `intent`, crea los `CampaignSend`
   * (PENDIENTE) y dispara el envío real vía el servicio IA (fire-and-forget,
   * mismo patrón que `notifyCallProfiling` de elevenlabs.service.ts). Nunca
   * espera a que se envíe nada — responde apenas queda encolado.
   */
  async send(tenantId: string, campaignId: string, dto: SendCampaignDto) {
    const campaign = await this.findOne(tenantId, campaignId);

    // distinct por customerId: si un mismo cliente tiene 2+ leads abiertos del
    // mismo intent (ej. auto + hogar, ambos CALIENTE), no se le manda 2 veces.
    const leads = await this.prisma.lead.findMany({
      where: {
        teamId: tenantId,
        intent: dto.intent,
        status: { in: OPEN_STATUSES },
        customer: { consentData: true, phone: { not: null } },
      },
      include: { customer: true },
      distinct: ['customerId'],
    });

    if (leads.length > MAX_SEGMENT_SIZE) {
      throw new BadRequestException(
        `El segmento "${dto.intent}" tiene ${leads.length} leads; el máximo por envío es ` +
          `${MAX_SEGMENT_SIZE}. Acota el segmento (ej. por país) antes de reintentar.`,
      );
    }
    if (!leads.length) {
      return { queued: 0, campaignId };
    }

    await this.prisma.campaignSend.createMany({
      data: leads.map((lead) => ({
        campaignId,
        leadId: lead.id,
        customerId: lead.customerId,
        intent: lead.intent,
      })),
      skipDuplicates: true, // protege contra doble POST /send de la misma campaña
    });

    const pending = await this.prisma.campaignSend.findMany({
      where: { campaignId, leadId: { in: leads.map((l) => l.id) }, status: 'PENDIENTE' },
    });
    const phoneByLeadId = new Map(leads.map((l) => [l.id, l.customer.phone]));
    // El link va al final del texto (reduce la pinta de "bulk" de un link-preview
    // arriba); si más adelante hay canal EMAIL real, ese va con adjunto, no link.
    const messageBody = campaign.bannerUrl
      ? `${dto.message}\n${campaign.bannerUrl}`
      : dto.message;
    const sends: BroadcastSend[] = pending
      .filter((s) => s.leadId && phoneByLeadId.get(s.leadId))
      .map((s) => ({ send_id: s.id, phone: phoneByLeadId.get(s.leadId as string) as string, message: messageBody }));

    this.dispatchBroadcast(tenantId, sends);

    return { queued: sends.length, campaignId };
  }

  updateSendStatus(sendId: string, dto: UpdateCampaignSendDto) {
    return this.prisma.campaignSend.update({
      where: { id: sendId },
      data: {
        status: dto.status,
        error: dto.error,
        sentAt: dto.status === 'ENVIADO' ? new Date() : undefined,
      },
    });
  }

  /**
   * Barrido cada 15 min (mismo patrón que `LeadScoringService.sweep`, ver
   * lead-scoring.service.ts:70): si el servicio IA nunca llamó de vuelta
   * (proceso caído, gateway inalcanzable en el connect) las filas quedarían
   * en PENDIENTE para siempre — esto las reconcilia a FALLIDO.
   */
  @Cron('*/15 * * * *')
  async reconcileStalePending(): Promise<void> {
    const staleBefore = new Date(Date.now() - STALE_PENDING_MINUTES * 60 * 1000);
    const { count } = await this.prisma.campaignSend.updateMany({
      where: { status: 'PENDIENTE', createdAt: { lt: staleBefore } },
      data: { status: 'FALLIDO', error: 'timeout: sin respuesta del servicio de envío' },
    });
    if (count) {
      this.logger.warn(`reconciliados ${count} CampaignSend atascados en PENDIENTE (>${STALE_PENDING_MINUTES}min)`);
    }
  }

  private dispatchBroadcast(tenantId: string, sends: BroadcastSend[]): void {
    if (!sends.length) return;
    const baseUrl = this.config.get<string>('AI_SERVICE_URL') ?? 'http://seguria-ai:8085';
    const serviceKey = this.config.get<string>('SERVICE_API_KEY') ?? 'demo-service-2026';
    fetch(`${baseUrl}/api/marketing/campaigns/broadcast`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Service-Key': serviceKey },
      body: JSON.stringify({ tenant_id: tenantId, sends }),
      signal: AbortSignal.timeout(5000),
    }).catch((err: unknown) =>
      this.logger.warn(`no se pudo disparar el broadcast de campaña: ${String(err)}`),
    );
  }
}
