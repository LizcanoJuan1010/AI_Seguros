import { Injectable } from '@nestjs/common';
import {
  Channel,
  InsuranceType,
  LeadIntent,
  LeadStatus,
} from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  AgentPerformanceQueryDto,
  CustomerPortfolioQueryDto,
  HotLeadsQueryDto,
  RiskLevel,
} from './dashboard.dto';

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

interface PortfolioSqlRow {
  id: string;
  full_name: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  document_id: string | null;
  created_at: Date;
  lead_id: string | null;
  lead_status: LeadStatus | null;
  intent: LeadIntent | null;
  priority_score: number | null;
  first_channel: Channel | null;
  highest_channel: Channel | null;
  insurance_type: InsuranceType | null;
  last_customer_response_at: Date | null;
  first_contact_at: Date | null;
  lead_created_at: Date | null;
  agent_name: string | null;
  active_policies: bigint | null;
  total_policies: bigint | null;
  premium_cop: Prisma.Decimal | null;
  open_claims: bigint | null;
  total_claims: bigint | null;
  max_fraud_score: Prisma.Decimal | null;
  total_calls: bigint | null;
  last_call_at: Date | null;
}

export interface PortfolioCustomer {
  customerId: string;
  fullName: string | null;
  phone: string | null;
  email: string | null;
  city: string | null;
  documentId: string | null;
  createdAt: Date;
  lead: {
    id: string;
    status: LeadStatus;
    intent: LeadIntent;
    priorityScore: number;
    firstChannel: Channel | null;
    highestChannel: Channel | null;
    insuranceType: InsuranceType | null;
    agentName: string | null;
    hoursSinceResponse: number | null;
    uncontacted: boolean;
  } | null;
  policies: { active: number; total: number; monthlyPremiumCop: number };
  claims: { open: number; total: number; maxFraudScore: number | null };
  calls: { total: number; lastAt: Date | null };
  risk: { level: RiskLevel; factors: string[] };
}

const HOURS_STALE_MEDIO = 24;
const HOURS_STALE_ALTO = 48;
const SCORE_URGENTE = 700;
const SCORE_SEGUIMIENTO = 400;
const FRAUD_THRESHOLD = 0.5;

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

  /**
   * Cartera de clientes 360° para el panel del gerente: cada cliente del
   * tenant con su lead más relevante (el abierto más reciente, o el último
   * cerrado), pólizas vigentes, reclamos, llamadas IA y un nivel de riesgo
   * explicable derivado de las mismas señales del motor de scoring
   * (priorityScore, silencio del cliente, fraude en reclamos). El `summary`
   * son los totales del tenant SIN filtros; `data` sí respeta search/intent/
   * status/insuranceType/risk y se pagina en memoria (cartera acotada a 500).
   */
  async customerPortfolio(tenantId: string, query: CustomerPortfolioQueryDto) {
    const rows = await this.prisma.$queryRaw<PortfolioSqlRow[]>(Prisma.sql`
      -- Los enums salen en su valor de BD (minúscula); UPPER() los alinea con
      -- los nombres del cliente Prisma ('nuevo' -> 'NUEVO') que usa la API.
      SELECT c.id, c.full_name, c.phone, c.email, c.city, c.document_id,
             c.created_at,
             l.id AS lead_id,
             UPPER(l.status::text) AS lead_status,
             UPPER(l.intent::text) AS intent,
             l.priority_score,
             UPPER(l.first_channel::text) AS first_channel,
             UPPER(l.highest_channel::text) AS highest_channel,
             UPPER(l.insurance_type::text) AS insurance_type,
             l.last_customer_response_at,
             l.first_contact_at, l.created_at AS lead_created_at,
             u.full_name AS agent_name,
             pol.active_policies, pol.total_policies, pol.premium_cop,
             cl.open_claims, cl.total_claims, cl.max_fraud_score,
             ac.total_calls, ac.last_call_at
      -- Siempre "public.": el search_path del usuario de BD antepone el
      -- esquema "seguria" (servicio IA), cuyo "leads" es otra tabla.
      FROM public.customers c
      LEFT JOIN LATERAL (
        SELECT * FROM public.leads
        WHERE customer_id = c.id
        ORDER BY (status IN ('nuevo','contactado','cotizado','negociacion')) DESC,
                 created_at DESC
        LIMIT 1
      ) l ON TRUE
      LEFT JOIN public.users u ON u.id = l.agent_id
      LEFT JOIN LATERAL (
        SELECT COUNT(*) FILTER (WHERE status = 'vigente') AS active_policies,
               COUNT(*) AS total_policies,
               COALESCE(SUM(monthly_premium_cop) FILTER (WHERE status = 'vigente'), 0)
                 AS premium_cop
        FROM public.policies WHERE customer_id = c.id
      ) pol ON TRUE
      LEFT JOIN LATERAL (
        SELECT COUNT(*) FILTER (
                 WHERE status IN ('reportado','en_revision','docs_pendientes')
               ) AS open_claims,
               COUNT(*) AS total_claims,
               MAX(fraud_score) AS max_fraud_score
        FROM public.claims WHERE customer_id = c.id
      ) cl ON TRUE
      LEFT JOIN LATERAL (
        SELECT COUNT(*) AS total_calls, MAX(started_at) AS last_call_at
        FROM public.ai_calls WHERE customer_id = c.id
      ) ac ON TRUE
      WHERE c.team_id = ${tenantId}::uuid
      ORDER BY l.priority_score DESC NULLS LAST, c.created_at DESC
      LIMIT 500
    `);

    const customers = rows.map((row) => this.toPortfolioCustomer(row));
    const summary = this.portfolioSummary(customers);

    const search = query.search?.trim().toLowerCase();
    const filtered = customers.filter((c) => {
      if (query.intent && c.lead?.intent !== query.intent) return false;
      if (query.status && c.lead?.status !== query.status) return false;
      if (
        query.insuranceType &&
        c.lead?.insuranceType !== query.insuranceType
      ) {
        return false;
      }
      if (query.risk && c.risk.level !== query.risk) return false;
      if (search) {
        const haystack = [c.fullName, c.phone, c.email, c.documentId, c.city]
          .filter(Boolean)
          .join(' ')
          .toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });

    const { skip, take } = paginationArgs(query.page, query.limit);
    return {
      summary,
      ...paginated(
        filtered.slice(skip, skip + take),
        filtered.length,
        query.page,
        query.limit,
      ),
    };
  }

  private toPortfolioCustomer(row: PortfolioSqlRow): PortfolioCustomer {
    const openLead =
      row.lead_id != null &&
      row.lead_status != null &&
      OPEN_STATUSES.includes(row.lead_status);

    const reference = row.last_customer_response_at ?? row.lead_created_at;
    const hoursSinceResponse =
      openLead && reference
        ? Math.floor((Date.now() - reference.getTime()) / 3_600_000)
        : null;
    const uncontacted = openLead && row.first_contact_at == null;
    const priorityScore = Number(row.priority_score ?? 0);
    const maxFraudScore =
      row.max_fraud_score != null ? Number(row.max_fraud_score) : null;
    const openClaims = Number(row.open_claims ?? 0);

    // Riesgo explicable: cada factor es una frase lista para el tooltip del
    // gerente. "Alto" = riesgo de perder la venta o fraude probable.
    const alto: string[] = [];
    const medio: string[] = [];
    if (openLead) {
      if (row.intent === LeadIntent.CALIENTE && uncontacted) {
        alto.push('Lead caliente sin primer contacto');
      }
      if (priorityScore > SCORE_URGENTE) {
        alto.push(`Prioridad urgente en cola (score ${priorityScore})`);
      } else if (priorityScore >= SCORE_SEGUIMIENTO) {
        medio.push(`En cola de seguimiento (score ${priorityScore})`);
      }
      if (hoursSinceResponse != null) {
        if (hoursSinceResponse > HOURS_STALE_ALTO) {
          alto.push(`Cliente sin responder hace ${hoursSinceResponse} h`);
        } else if (hoursSinceResponse > HOURS_STALE_MEDIO) {
          medio.push(`Cliente sin responder hace ${hoursSinceResponse} h`);
        }
      }
    }
    if (maxFraudScore != null && maxFraudScore >= FRAUD_THRESHOLD) {
      alto.push(`Posible fraude en reclamo (score ${maxFraudScore.toFixed(2)})`);
    } else if (openClaims > 0) {
      medio.push(`${openClaims} reclamo(s) abierto(s) en gestión`);
    }

    const level: RiskLevel = alto.length ? 'alto' : medio.length ? 'medio' : 'bajo';

    return {
      customerId: row.id,
      fullName: row.full_name,
      phone: row.phone,
      email: row.email,
      city: row.city,
      documentId: row.document_id,
      createdAt: row.created_at,
      lead:
        row.lead_id && row.lead_status && row.intent
          ? {
              id: row.lead_id,
              status: row.lead_status,
              intent: row.intent,
              priorityScore,
              firstChannel: row.first_channel,
              highestChannel: row.highest_channel,
              insuranceType: row.insurance_type,
              agentName: row.agent_name,
              hoursSinceResponse,
              uncontacted,
            }
          : null,
      policies: {
        active: Number(row.active_policies ?? 0),
        total: Number(row.total_policies ?? 0),
        monthlyPremiumCop: Number(row.premium_cop ?? 0),
      },
      claims: { open: openClaims, total: Number(row.total_claims ?? 0), maxFraudScore },
      calls: { total: Number(row.total_calls ?? 0), lastAt: row.last_call_at },
      risk: { level, factors: [...alto, ...medio] },
    };
  }

  private portfolioSummary(customers: PortfolioCustomer[]) {
    const open = customers.filter(
      (c) => c.lead && OPEN_STATUSES.includes(c.lead.status),
    );
    const byIntent = { caliente: 0, tibio: 0, frio: 0 };
    for (const c of open) {
      if (c.lead!.intent === LeadIntent.CALIENTE) byIntent.caliente += 1;
      else if (c.lead!.intent === LeadIntent.TIBIO) byIntent.tibio += 1;
      else byIntent.frio += 1;
    }
    const byRisk = { alto: 0, medio: 0, bajo: 0 };
    for (const c of customers) byRisk[c.risk.level] += 1;

    return {
      totalCustomers: customers.length,
      openLeads: open.length,
      hotUncontacted: open.filter(
        (c) => c.lead!.intent === LeadIntent.CALIENTE && c.lead!.uncontacted,
      ).length,
      unresponsive48h: open.filter(
        (c) =>
          c.lead!.hoursSinceResponse != null &&
          c.lead!.hoursSinceResponse > HOURS_STALE_ALTO,
      ).length,
      activePolicies: customers.reduce((s, c) => s + c.policies.active, 0),
      monthlyPremiumCop: customers.reduce(
        (s, c) => s + c.policies.monthlyPremiumCop,
        0,
      ),
      openClaims: customers.reduce((s, c) => s + c.claims.open, 0),
      fraudSuspects: customers.filter(
        (c) =>
          c.claims.maxFraudScore != null &&
          c.claims.maxFraudScore >= FRAUD_THRESHOLD,
      ).length,
      byIntent,
      byRisk,
    };
  }
}
