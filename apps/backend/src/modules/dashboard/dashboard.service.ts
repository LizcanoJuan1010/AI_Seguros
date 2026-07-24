import { Injectable } from '@nestjs/common';
import { Channel, LeadIntent, LeadStatus } from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { AgentPerformanceQueryDto, HotLeadsQueryDto } from './dashboard.dto';

interface CountRow {
  total: bigint;
}

interface AgentPerformanceRow {
  agent_id: string;
  full_name: string;
  team_id: string | null;
  leads_recibidos: bigint;
  llamadas_realizadas: bigint;
  polizas_cerradas: bigint;
  conversion_pct: Prisma.Decimal | null;
  revenue_mensual_cop: Prisma.Decimal;
}

interface DailyKpisRow {
  llamadas_ia_hoy: bigint;
  duracion_promedio_sec: Prisma.Decimal | null;
  polizas_hoy: bigint;
  revenue_hoy_cop: Prisma.Decimal;
}

const OPEN_STATUSES: LeadStatus[] = [
  LeadStatus.NUEVO,
  LeadStatus.CONTACTADO,
  LeadStatus.COTIZADO,
  LeadStatus.NEGOCIACION,
];

@Injectable()
export class DashboardService {
  constructor(private readonly prisma: PrismaService) {}

  async agentPerformance(tenantId: string, query: AgentPerformanceQueryDto) {
    const { skip, take } = paginationArgs(query.page, query.limit);
    // v_agent_performance expone team_id (el equipo del agente). Se aísla por
    // tenant filtrando siempre por el team resuelto del header X-Tenant-Id.
    const where = Prisma.sql`WHERE team_id = ${tenantId}::uuid`;
    const direction =
      query.order === 'asc' ? Prisma.sql`ASC` : Prisma.sql`DESC`;

    const [rows, count] = await Promise.all([
      this.prisma.$queryRaw<AgentPerformanceRow[]>(Prisma.sql`
        SELECT * FROM v_agent_performance
        ${where}
        ORDER BY full_name ${direction}
        LIMIT ${take} OFFSET ${skip}
      `),
      this.prisma.$queryRaw<CountRow[]>(Prisma.sql`
        SELECT COUNT(*) AS total FROM v_agent_performance
        ${where}
      `),
    ]);

    const data = rows.map((row) => ({
      agentId: row.agent_id,
      fullName: row.full_name,
      teamId: row.team_id,
      leadsRecibidos: Number(row.leads_recibidos),
      llamadasRealizadas: Number(row.llamadas_realizadas),
      polizasCerradas: Number(row.polizas_cerradas),
      conversionPct: row.conversion_pct,
      revenueMensualCop: row.revenue_mensual_cop,
    }));

    return paginated(
      data,
      Number(count[0]?.total ?? 0),
      query.page,
      query.limit,
    );
  }

  async dailyKpis(tenantId: string) {
    // Métricas de pólizas del día scoped por tenant (policies.team_id).
    // Las métricas de llamadas IA quedan globales: AiCall aún no tiene team_id
    // en este alcance (ver "pendiente" en la doc de multitenancy).
    const [callsRow] = await this.prisma.$queryRaw<
      Pick<DailyKpisRow, 'llamadas_ia_hoy' | 'duracion_promedio_sec'>[]
    >`
      SELECT
        COUNT(*) FILTER (WHERE started_at::DATE = CURRENT_DATE) AS llamadas_ia_hoy,
        ROUND(AVG(duration_sec) FILTER (WHERE status = 'completada'), 0)
          AS duracion_promedio_sec
      FROM ai_calls
    `;

    const [policyRow] = await this.prisma.$queryRaw<
      Pick<DailyKpisRow, 'polizas_hoy' | 'revenue_hoy_cop'>[]
    >(Prisma.sql`
      SELECT
        COUNT(*)::bigint AS polizas_hoy,
        COALESCE(SUM(monthly_premium_cop), 0) AS revenue_hoy_cop
      FROM policies
      WHERE created_at::DATE = CURRENT_DATE
        AND team_id = ${tenantId}::uuid
    `);

    return {
      llamadasIaHoy: Number(callsRow?.llamadas_ia_hoy ?? 0),
      duracionPromedioSec: callsRow?.duracion_promedio_sec ?? null,
      polizasHoy: Number(policyRow?.polizas_hoy ?? 0),
      revenueHoyCop: policyRow?.revenue_hoy_cop ?? new Prisma.Decimal(0),
    };
  }

  async aiImpact(tenantId: string) {
    // La velocidad de cotización/cierre sale del funnel conversacional (esquema
    // `seguria` del servicio IA, mismo Postgres); las pólizas y reclamos del
    // dominio (public) van scoped por tenant. Cada bloque degrada a null si su
    // esquema/tabla aún no existe.
    let avgQuoteMinutes: number | null = null;
    let avgCloseDays: number | null = null;
    let conversionPct: number | null = null;
    try {
      const [funnel] = await this.prisma.$queryRaw<
        {
          quote_mins: number | null;
          close_days: number | null;
          conversion_pct: number | null;
        }[]
      >`
        SELECT
          (SELECT (AVG(EXTRACT(EPOCH FROM (fq.first_q - l.created_at))) / 60.0)::float8
             FROM seguria.leads l
             JOIN (SELECT lead_id, MIN(created_at) AS first_q
                     FROM seguria.quotes GROUP BY lead_id) fq ON fq.lead_id = l.id
            WHERE fq.first_q >= l.created_at) AS quote_mins,
          (SELECT (AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) / 86400.0)::float8
             FROM seguria.leads WHERE stage = 'cerrado') AS close_days,
          (SELECT CASE WHEN COUNT(*) = 0 THEN NULL
                       ELSE (100.0 * COUNT(*) FILTER (WHERE stage = 'cerrado')
                             / COUNT(*))::float8 END
             FROM seguria.leads) AS conversion_pct
      `;
      avgQuoteMinutes = funnel?.quote_mins ?? null;
      avgCloseDays = funnel?.close_days ?? null;
      conversionPct = funnel?.conversion_pct ?? null;
    } catch {
      // esquema seguria no disponible
    }

    const [pol] = await this.prisma.$queryRaw<
      { total: bigint; auto: bigint }[]
    >(Prisma.sql`
      SELECT COUNT(*)::bigint AS total,
             COUNT(*) FILTER (WHERE agent_id IS NULL)::bigint AS auto
      FROM policies
      WHERE team_id = ${tenantId}::uuid
    `);
    const policiesTotal = Number(pol?.total ?? 0);
    const autoEmissionPct =
      policiesTotal > 0 ? (100 * Number(pol?.auto ?? 0)) / policiesTotal : null;

    let claimsCycleDays: number | null = null;
    let claimsOpen = 0;
    try {
      const [claims] = await this.prisma.$queryRaw<
        { cycle_days: number | null; open: bigint }[]
      >(Prisma.sql`
        SELECT (AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) / 86400.0)
                 FILTER (WHERE status IN ('aprobado', 'pagado'))::float8 AS cycle_days,
               COUNT(*) FILTER (WHERE status IN ('reportado', 'en_revision',
                                                 'docs_pendientes'))::bigint AS open
        FROM claims
        WHERE team_id = ${tenantId}::uuid
      `);
      claimsCycleDays = claims?.cycle_days ?? null;
      claimsOpen = Number(claims?.open ?? 0);
    } catch {
      // tabla claims aún no migrada
    }

    return {
      avgQuoteMinutes,
      avgCloseDays,
      conversionPct,
      policiesTotal,
      autoEmissionPct,
      claimsCycleDays,
      claimsOpen,
    };
  }

  /**
   * Generaliza `v_hot_leads_uncontacted` (antes hardcodeada: intent=caliente,
   * status=nuevo, >2h). Los filtros ahora son query params con esos mismos
   * defaults, sobre `leads` directo (ya no la vista) — puede porque
   * `firstContactAt`/`createdAt` ya alcanzan sin necesitar SQL crudo.
   */
  async hotLeadsUncontacted(tenantId: string, query: HotLeadsQueryDto) {
    const staleHours = query.staleHours ?? 2;
    const cutoff = new Date(Date.now() - staleHours * 3_600_000);
    const where: Prisma.LeadWhereInput = {
      teamId: tenantId,
      intent: query.intent ?? LeadIntent.CALIENTE,
      status: query.status ?? LeadStatus.NUEVO,
      firstContactAt: null,
      createdAt: { lt: cutoff },
      ...(query.agentId && { agentId: query.agentId }),
      ...(query.unassignedOnly && { agentId: null }),
    };

    const [data, total] = await Promise.all([
      this.prisma.lead.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
        include: { agent: { select: { fullName: true } } },
      }),
      this.prisma.lead.count({ where }),
    ]);

    const mapped = data.map((lead) => ({
      id: lead.id,
      agentId: lead.agentId,
      agentName: lead.agent?.fullName ?? null,
      createdAt: lead.createdAt,
      horasSinContacto: Math.floor(
        (Date.now() - lead.createdAt.getTime()) / 3_600_000,
      ),
    }));

    return paginated(mapped, total, query.page, query.limit);
  }

  /** KPIs de velocidad de respuesta y clusterización (motor de leads). */
  async leadsKpis(tenantId: string) {
    const [firstResponseRow] = await this.prisma.$queryRaw<
      { avg_hours: number | null }[]
    >(Prisma.sql`
      SELECT AVG(EXTRACT(EPOCH FROM (first_touch.ts - l.created_at)) / 3600) AS avg_hours
      FROM public.leads l
      JOIN LATERAL (
        SELECT MIN(ts) AS ts FROM (
          SELECT le.created_at AS ts FROM public.lead_events le
          WHERE le.lead_id = l.id
            AND le.event_type IN ('llamada_saliente','whatsapp','email','reunion')
          UNION ALL
          SELECT cm.spoken_at AS ts FROM public.call_messages cm
          JOIN public.ai_calls ac ON ac.id = cm.call_id
          WHERE ac.customer_id = l.customer_id AND cm.speaker = 'ia'
        ) touches
      ) first_touch ON true
      WHERE l.team_id = ${tenantId}::uuid
    `);

    const [latencyRow] = await this.prisma.$queryRaw<
      { avg_minutes: number | null }[]
    >(Prisma.sql`
      SELECT AVG(EXTRACT(EPOCH FROM (cliente_ts - prev_ts)) / 60) AS avg_minutes
      FROM (
        SELECT cm.spoken_at AS cliente_ts,
               LAG(cm.spoken_at) OVER (PARTITION BY cm.call_id ORDER BY cm.spoken_at) AS prev_ts,
               LAG(cm.speaker) OVER (PARTITION BY cm.call_id ORDER BY cm.spoken_at) AS prev_speaker
        FROM public.call_messages cm
        JOIN public.ai_calls ac ON ac.id = cm.call_id
        WHERE ac.team_id = ${tenantId}::uuid AND cm.speaker = 'cliente'
      ) turns
      WHERE prev_speaker = 'ia'
    `);

    const [staleRow] = await this.prisma.$queryRaw<
      { total: bigint; stale: bigint }[]
    >(Prisma.sql`
      SELECT COUNT(*) AS total,
             COUNT(*) FILTER (
               WHERE now() - COALESCE(last_customer_response_at, created_at) > interval '48 hours'
             ) AS stale
      FROM public.leads
      WHERE team_id = ${tenantId}::uuid
        AND status IN ('nuevo','contactado','cotizado','negociacion')
    `);

    const intentGroups = await this.prisma.lead.groupBy({
      by: ['intent'],
      where: { teamId: tenantId, status: { in: OPEN_STATUSES } },
      _count: { _all: true },
    });

    const totalOpen = Number(staleRow?.total ?? 0);
    return {
      avgFirstResponseHours: firstResponseRow?.avg_hours ?? null,
      avgCustomerResponseMinutes: latencyRow?.avg_minutes ?? null,
      unresponsiveOver48h: {
        total: totalOpen,
        stale: Number(staleRow?.stale ?? 0),
        pct: totalOpen ? Number(staleRow?.stale ?? 0) / totalOpen : 0,
      },
      intentDistribution: intentGroups.map((g) => ({
        intent: g.intent,
        count: g._count._all,
      })),
    };
  }

  /** Progresión de canal (click/interés -> WhatsApp -> llamada) y conversión por canal. */
  async channelFunnel(tenantId: string) {
    const [totalsByChannel, wonByChannel, escalationRow] = await Promise.all([
      this.prisma.lead.groupBy({
        by: ['firstChannel'],
        where: { teamId: tenantId, firstChannel: { not: null } },
        _count: { _all: true },
      }),
      this.prisma.lead.groupBy({
        by: ['firstChannel'],
        where: {
          teamId: tenantId,
          firstChannel: { not: null },
          status: LeadStatus.CERRADO_GANADO,
        },
        _count: { _all: true },
      }),
      this.prisma.$queryRaw<
        { total: bigint; escalated: bigint; reached_call: bigint }[]
      >(Prisma.sql`
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE highest_channel IS DISTINCT FROM first_channel) AS escalated,
               COUNT(*) FILTER (WHERE highest_channel = 'voice_call') AS reached_call
        FROM public.leads
        WHERE team_id = ${tenantId}::uuid AND first_channel IS NOT NULL
      `),
    ]);

    const wonMap = new Map(
      wonByChannel.map((r) => [r.firstChannel, r._count._all]),
    );
    const total = Number(escalationRow[0]?.total ?? 0);

    return {
      conversionByFirstChannel: totalsByChannel.map((r) => {
        const won = wonMap.get(r.firstChannel) ?? 0;
        return {
          channel: r.firstChannel as Channel | null,
          total: r._count._all,
          won,
          conversionPct: r._count._all ? won / r._count._all : 0,
        };
      }),
      channelEscalationRate: total
        ? Number(escalationRow[0].escalated) / total
        : 0,
      reachedVoiceCallPct: total
        ? Number(escalationRow[0].reached_call) / total
        : 0,
    };
  }

  /** Profundidad y salud de la cola priorizada por agente. */
  async queueHealth(tenantId: string) {
    const leads = await this.prisma.lead.findMany({
      where: { teamId: tenantId, status: { in: OPEN_STATUSES } },
      select: { agentId: true, priorityScore: true },
    });

    const byAgent = new Map<
      string | null,
      { count: number; scoreSum: number; urgent: number; normal: number; low: number }
    >();
    for (const lead of leads) {
      const bucket = byAgent.get(lead.agentId) ?? {
        count: 0,
        scoreSum: 0,
        urgent: 0,
        normal: 0,
        low: 0,
      };
      bucket.count += 1;
      bucket.scoreSum += lead.priorityScore;
      if (lead.priorityScore > 700) bucket.urgent += 1;
      else if (lead.priorityScore >= 400) bucket.normal += 1;
      else bucket.low += 1;
      byAgent.set(lead.agentId, bucket);
    }

    return Array.from(byAgent.entries()).map(([agentId, b]) => ({
      agentId,
      total: b.count,
      avgPriorityScore: b.count ? Math.round(b.scoreSum / b.count) : 0,
      urgent: b.urgent,
      normal: b.normal,
      low: b.low,
    }));
  }
}
