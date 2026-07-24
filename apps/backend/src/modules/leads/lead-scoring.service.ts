import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import {
  Channel,
  EventType,
  LeadIntent,
  LeadStatus,
  SpeakerType,
} from '../../generated/prisma/enums';
import { Lead, Prisma } from '../../generated/prisma/client';
import { PrismaService } from '../../prisma/prisma.service';
import { CHANNEL_RANK, higherChannel } from './channel-rank';
import { LeadScoringConfigService } from './lead-scoring.config';

const OPEN_STATUSES: LeadStatus[] = [
  LeadStatus.NUEVO,
  LeadStatus.CONTACTADO,
  LeadStatus.COTIZADO,
  LeadStatus.NEGOCIACION,
];

const OUTBOUND_EVENT_TYPES: EventType[] = [
  EventType.LLAMADA_SALIENTE,
  EventType.WHATSAPP,
  EventType.EMAIL,
  EventType.REUNION,
];

interface LeadSignals {
  highestChannel: Channel | null;
  lastCustomerResponseAt: Date | null;
  lastOutboundAt: Date | null;
}

function maxDate(...dates: Array<Date | null | undefined>): Date | null {
  const valid = dates.filter((d): d is Date => !!d);
  if (!valid.length) return null;
  return valid.reduce((a, b) => (b > a ? b : a));
}

/**
 * Motor de clusterización de leads (frío/tibio/caliente) y de la cola
 * priorizada (`priorityScore`). Reglas explicables, no ML — ver
 * docs del plan. `recomputeOne`/`recomputeForCustomer` los disparan los
 * hooks de escritura (LeadEvent, CallMessage); `sweep()` (cron cada 15 min +
 * una pasada al boot) es lo único que detecta el "silencio puro" (un lead
 * que dejó de responder sin generar ningún evento nuevo).
 *
 * IMPORTANTE: `Lead.updated_at` lo pisa un trigger de Postgres en CUALQUIER
 * UPDATE. Por eso `applyScoring` compara valores calculados vs. guardados y
 * solo escribe si algo realmente cambió — si no, updatedAt quedaría "ahora"
 * en cada barrido y dejaría de servir como señal de nada.
 */
@Injectable()
export class LeadScoringService implements OnModuleInit {
  private readonly logger = new Logger(LeadScoringService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly scoringConfig: LeadScoringConfigService,
  ) {}

  async onModuleInit(): Promise<void> {
    // No bloquea el arranque del módulo; corre en background.
    void this.sweepOnce().catch((err) =>
      this.logger.warn(`sweep inicial falló: ${err}`),
    );
  }

  @Cron('*/15 * * * *')
  async sweep(): Promise<void> {
    await this.sweepOnce();
  }

  async recomputeOne(leadId: string): Promise<void> {
    const lead = await this.prisma.lead.findUnique({ where: { id: leadId } });
    if (!lead) return;
    await this.applyScoring(lead);
  }

  async recomputeForCustomer(
    tenantId: string,
    customerId: string,
  ): Promise<void> {
    const leads = await this.prisma.lead.findMany({
      where: { teamId: tenantId, customerId, status: { in: OPEN_STATUSES } },
    });
    for (const lead of leads) {
      await this.applyScoring(lead);
    }
  }

  private async sweepOnce(): Promise<void> {
    const BATCH = 500;
    let cursor: string | undefined;
    for (;;) {
      const leads = await this.prisma.lead.findMany({
        where: {
          status: { in: OPEN_STATUSES },
          ...(cursor && { id: { gt: cursor } }),
        },
        orderBy: { id: 'asc' },
        take: BATCH,
      });
      if (!leads.length) break;
      for (const lead of leads) {
        try {
          await this.applyScoring(lead);
        } catch (err) {
          this.logger.warn(`recompute falló para lead ${lead.id}: ${err}`);
        }
      }
      cursor = leads[leads.length - 1].id;
      if (leads.length < BATCH) break;
    }
  }

  private async computeSignals(lead: Lead): Promise<LeadSignals> {
    const [lastCustomerMsg, lastAgentMsg, lastOutboundEvent, calls] =
      await Promise.all([
        this.prisma.callMessage.findFirst({
          where: {
            speaker: SpeakerType.CLIENTE,
            call: { customerId: lead.customerId },
          },
          orderBy: { spokenAt: 'desc' },
          select: { spokenAt: true },
        }),
        this.prisma.callMessage.findFirst({
          where: {
            speaker: SpeakerType.IA,
            call: { customerId: lead.customerId },
          },
          orderBy: { spokenAt: 'desc' },
          select: { spokenAt: true },
        }),
        this.prisma.leadEvent.findFirst({
          where: { leadId: lead.id, eventType: { in: OUTBOUND_EVENT_TYPES } },
          orderBy: { createdAt: 'desc' },
          select: { createdAt: true },
        }),
        this.prisma.aiCall.findMany({
          where: { customerId: lead.customerId },
          distinct: ['channel'],
          select: { channel: true },
        }),
      ]);

    const observedChannel = calls.reduce<Channel | null>(
      (acc, c) => higherChannel(acc, c.channel),
      null,
    );
    const highestChannel = observedChannel
      ? higherChannel(lead.highestChannel, observedChannel)
      : lead.highestChannel;

    return {
      highestChannel,
      lastCustomerResponseAt: maxDate(
        lead.lastCustomerResponseAt,
        lastCustomerMsg?.spokenAt,
      ),
      lastOutboundAt: maxDate(
        lead.lastOutboundAt,
        lastAgentMsg?.spokenAt,
        lastOutboundEvent?.createdAt,
      ),
    };
  }

  private decideIntentAndScore(
    lead: Lead,
    signals: LeadSignals,
    now: Date,
  ): { intent: LeadIntent; priorityScore: number } {
    const cfg = this.scoringConfig.get();

    // Override manual (PATCH /leads/:id) vigente: el motor no toca `intent`,
    // pero sí sigue recalculando el priorityScore con ese intent fijo.
    if (lead.intentOverride && lead.intentOverrideAt) {
      const overrideAgeDays =
        (now.getTime() - lead.intentOverrideAt.getTime()) / 86_400_000;
      if (overrideAgeDays < cfg.overrideDays) {
        const priorityScore = this.computeScore(
          lead,
          signals,
          lead.intentOverride,
          now,
        );
        return { intent: lead.intentOverride, priorityScore };
      }
    }

    const reference = signals.lastCustomerResponseAt ?? lead.createdAt;
    const hoursSinceResponse = (now.getTime() - reference.getTime()) / 3_600_000;
    const staleThreshold = this.scoringConfig.staleThreshold(lead.status);
    const hardThreshold = this.scoringConfig.hardThreshold(lead.status);
    const channelRank = CHANNEL_RANK[signals.highestChannel ?? Channel.WEB_INTEREST];

    let intent: LeadIntent;
    if (hoursSinceResponse >= hardThreshold) {
      intent = LeadIntent.FRIO;
    } else if (hoursSinceResponse >= staleThreshold) {
      // Un lead que sí escaló de canal se enfría más despacio (un nivel de gracia).
      intent = channelRank <= CHANNEL_RANK[Channel.WEB_INTEREST]
        ? LeadIntent.FRIO
        : LeadIntent.TIBIO;
    } else if (
      hoursSinceResponse <= cfg.responseFastHours &&
      (channelRank >= CHANNEL_RANK[Channel.VOICE_CALL] ||
        lead.status === LeadStatus.COTIZADO)
    ) {
      intent = LeadIntent.CALIENTE;
    } else {
      intent = LeadIntent.TIBIO;
    }

    const priorityScore = this.computeScore(lead, signals, intent, now);
    return { intent, priorityScore };
  }

  private computeScore(
    lead: Lead,
    signals: LeadSignals,
    intent: LeadIntent,
    now: Date,
  ): number {
    const cfg = this.scoringConfig.get();
    const reference = signals.lastCustomerResponseAt ?? lead.createdAt;
    const hoursSinceResponse = (now.getTime() - reference.getTime()) / 3_600_000;
    const staleThreshold = this.scoringConfig.staleThreshold(lead.status);
    const hardThreshold = this.scoringConfig.hardThreshold(lead.status);
    const r = staleThreshold > 0 ? hoursSinceResponse / staleThreshold : 0;
    const hardRatio = staleThreshold > 0 ? hardThreshold / staleThreshold : 1;

    let urgencyBonus: number;
    if (r < 1) {
      urgencyBonus = cfg.urgencyMax * r;
    } else if (r < hardRatio) {
      urgencyBonus =
        cfg.urgencyMax * (1 - (0.4 * (r - 1)) / Math.max(hardRatio - 1, 0.001));
    } else {
      urgencyBonus = Math.max(0, cfg.urgencyMax * 0.2 - 5 * (r - hardRatio));
    }

    const channelWeight =
      cfg.channelWeight[signals.highestChannel ?? Channel.WEB_INTEREST] ?? 0;
    const unassignedBonus = lead.agentId ? 0 : cfg.unassignedBonus;

    const raw =
      cfg.tempWeight[intent] + channelWeight + urgencyBonus + unassignedBonus;
    return Math.max(0, Math.min(1000, Math.round(raw)));
  }

  private async applyScoring(lead: Lead): Promise<void> {
    if (
      lead.status === LeadStatus.CERRADO_GANADO ||
      lead.status === LeadStatus.CERRADO_PERDIDO
    ) {
      return;
    }

    const now = new Date();
    const signals = await this.computeSignals(lead);
    const { intent, priorityScore } = this.decideIntentAndScore(
      lead,
      signals,
      now,
    );

    const changes: Prisma.LeadUncheckedUpdateInput = {};
    if (signals.highestChannel && signals.highestChannel !== lead.highestChannel) {
      changes.highestChannel = signals.highestChannel;
    }
    if (
      signals.lastCustomerResponseAt &&
      signals.lastCustomerResponseAt.getTime() !==
        (lead.lastCustomerResponseAt?.getTime() ?? 0)
    ) {
      changes.lastCustomerResponseAt = signals.lastCustomerResponseAt;
    }
    if (
      signals.lastOutboundAt &&
      signals.lastOutboundAt.getTime() !== (lead.lastOutboundAt?.getTime() ?? 0)
    ) {
      changes.lastOutboundAt = signals.lastOutboundAt;
    }
    const intentChanged = intent !== lead.intent;
    if (intentChanged) changes.intent = intent;
    if (priorityScore !== lead.priorityScore) {
      changes.priorityScore = priorityScore;
      changes.priorityScoreUpdatedAt = now;
    }

    if (Object.keys(changes).length === 0) return;

    await this.prisma.lead.update({ where: { id: lead.id }, data: changes });

    if (intentChanged) {
      await this.prisma.leadEvent.create({
        data: {
          leadId: lead.id,
          eventType: EventType.CAMBIO_ESTADO,
          notes: 'Auto-reclasificado por el motor de scoring',
          payload: {
            field: 'intent',
            from: lead.intent,
            to: intent,
          } as Prisma.InputJsonValue,
        },
      });
    }
  }
}
