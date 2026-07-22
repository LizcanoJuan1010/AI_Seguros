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

  async agentPerformance(query: AgentPerformanceQueryDto) {
    const { skip, take } = paginationArgs(query.page, query.limit);
    const where = query.teamId
      ? Prisma.sql`WHERE team_id = ${query.teamId}::uuid`
      : Prisma.empty;
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

  async dailyKpis() {
    const [row] = await this.prisma.$queryRaw<DailyKpisRow[]>`
      SELECT * FROM v_daily_kpis
    `;

    return {
      llamadasIaHoy: Number(row?.llamadas_ia_hoy ?? 0),
      duracionPromedioSec: row?.duracion_promedio_sec ?? null,
      polizasHoy: Number(row?.polizas_hoy ?? 0),
      revenueHoyCop: row?.revenue_hoy_cop ?? new Prisma.Decimal(0),
    };
  }

  async hotLeadsUncontacted(query: HotLeadsQueryDto) {
    const { skip, take } = paginationArgs(query.page, query.limit);
    const where = query.agentId
      ? Prisma.sql`WHERE agent_id = ${query.agentId}::uuid`
      : Prisma.empty;
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
