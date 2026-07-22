import { Injectable } from '@nestjs/common';
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

interface HotLeadRow {
  id: string;
  agent_id: string | null;
  agent_name: string | null;
  created_at: Date;
  tiempo_sin_contacto: string;
}

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

  async hotLeadsUncontacted(tenantId: string, query: HotLeadsQueryDto) {
    const { skip, take } = paginationArgs(query.page, query.limit);
    // v_hot_leads_uncontacted expone team_id; se aísla por tenant y, opcional,
    // por agente.
    const conditions: Prisma.Sql[] = [
      Prisma.sql`team_id = ${tenantId}::uuid`,
    ];
    if (query.agentId) {
      conditions.push(Prisma.sql`agent_id = ${query.agentId}::uuid`);
    }
    const where = Prisma.sql`WHERE ${Prisma.join(conditions, ' AND ')}`;
    const direction =
      query.order === 'asc' ? Prisma.sql`ASC` : Prisma.sql`DESC`;

    const [rows, count] = await Promise.all([
      this.prisma.$queryRaw<HotLeadRow[]>(Prisma.sql`
        SELECT id, agent_id, agent_name, created_at,
               tiempo_sin_contacto::text AS tiempo_sin_contacto
        FROM v_hot_leads_uncontacted
        ${where}
        ORDER BY created_at ${direction}
        LIMIT ${take} OFFSET ${skip}
      `),
      this.prisma.$queryRaw<CountRow[]>(Prisma.sql`
        SELECT COUNT(*) AS total FROM v_hot_leads_uncontacted
        ${where}
      `),
    ]);

    const data = rows.map((row) => ({
      id: row.id,
      agentId: row.agent_id,
      agentName: row.agent_name,
      createdAt: row.created_at,
      tiempoSinContacto: row.tiempo_sin_contacto,
    }));

    return paginated(
      data,
      Number(count[0]?.total ?? 0),
      query.page,
      query.limit,
    );
  }
}
