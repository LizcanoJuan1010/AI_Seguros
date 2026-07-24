import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Channel, LeadIntent, LeadStatus } from '../../generated/prisma/enums';

export interface LeadScoringConfig {
  staleHoursByStatus: Partial<Record<LeadStatus, number>>;
  hardStaleMultiplier: number;
  responseFastHours: number;
  responseMedHours: number;
  tempWeight: Record<LeadIntent, number>;
  channelWeight: Record<Channel, number>;
  unassignedBonus: number;
  urgencyMax: number;
  overrideDays: number;
}

/**
 * Todos los umbrales/pesos del motor de leads en un solo lugar, leídos de
 * env vars (nada hardcodeado en las fórmulas de lead-scoring.service.ts).
 * Las horas "sin respuesta" generalizan los números que ya usaba
 * `proactive.py` (2 días cotizado, 3 días documento, 1 día descubrimiento)
 * para mantener consistencia entre el motor Python y el de Prisma.
 */
@Injectable()
export class LeadScoringConfigService {
  private readonly cfg: LeadScoringConfig;

  constructor(config: ConfigService) {
    const num = (key: string, def: number): number => {
      const raw = config.get<string>(key);
      const parsed = raw !== undefined ? Number(raw) : NaN;
      return Number.isFinite(parsed) ? parsed : def;
    };

    this.cfg = {
      staleHoursByStatus: {
        [LeadStatus.NUEVO]: num('LEAD_SCORE_STALE_HOURS_NUEVO', 24),
        [LeadStatus.CONTACTADO]: num('LEAD_SCORE_STALE_HOURS_CONTACTADO', 24),
        [LeadStatus.COTIZADO]: num('LEAD_SCORE_STALE_HOURS_COTIZADO', 48),
        [LeadStatus.NEGOCIACION]: num('LEAD_SCORE_STALE_HOURS_NEGOCIACION', 72),
      },
      hardStaleMultiplier: num('LEAD_SCORE_HARD_MULTIPLIER', 2.5),
      responseFastHours: num('LEAD_SCORE_RESPONSE_FAST_HOURS', 4),
      responseMedHours: num('LEAD_SCORE_RESPONSE_MED_HOURS', 24),
      tempWeight: {
        [LeadIntent.CALIENTE]: num('LEAD_SCORE_WEIGHT_CALIENTE', 400),
        [LeadIntent.TIBIO]: num('LEAD_SCORE_WEIGHT_TIBIO', 200),
        [LeadIntent.FRIO]: num('LEAD_SCORE_WEIGHT_FRIO', 50),
      },
      channelWeight: {
        [Channel.WEB_INTEREST]: 0,
        [Channel.WHATSAPP]: num('LEAD_SCORE_WEIGHT_CHANNEL_MID', 50),
        [Channel.EMAIL]: num('LEAD_SCORE_WEIGHT_CHANNEL_MID', 50),
        [Channel.WEB_CHAT]: num('LEAD_SCORE_WEIGHT_CHANNEL_MID', 50),
        [Channel.VOICE_CALL]: num('LEAD_SCORE_WEIGHT_CHANNEL_CALL', 100),
      },
      unassignedBonus: num('LEAD_SCORE_UNASSIGNED_BONUS', 150),
      urgencyMax: num('LEAD_SCORE_URGENCY_MAX', 250),
      overrideDays: num('LEAD_SCORE_OVERRIDE_DAYS', 7),
    };
  }

  get(): LeadScoringConfig {
    return this.cfg;
  }

  staleThreshold(status: LeadStatus): number {
    return (
      this.cfg.staleHoursByStatus[status] ??
      this.cfg.staleHoursByStatus[LeadStatus.NUEVO]!
    );
  }

  hardThreshold(status: LeadStatus): number {
    return this.staleThreshold(status) * this.cfg.hardStaleMultiplier;
  }
}
