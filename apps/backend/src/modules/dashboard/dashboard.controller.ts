import { Controller, Get, Query, UseGuards } from '@nestjs/common';
import { OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { TenantId } from '../../common/tenant.decorator';
import { AgentPerformanceQueryDto, HotLeadsQueryDto } from './dashboard.dto';
import { DashboardService } from './dashboard.service';

@UseGuards(OptionalJwtAuthGuard)
@Controller('dashboard')
export class DashboardController {
  constructor(private readonly dashboardService: DashboardService) {}

  @Get('agent-performance')
  agentPerformance(
    @TenantId() tenantId: string,
    @Query() query: AgentPerformanceQueryDto,
  ) {
    return this.dashboardService.agentPerformance(tenantId, query);
  }

  @Get('daily-kpis')
  dailyKpis(@TenantId() tenantId: string) {
    return this.dashboardService.dailyKpis(tenantId);
  }

  @Get('ai-impact')
  aiImpact(@TenantId() tenantId: string) {
    return this.dashboardService.aiImpact(tenantId);
  }

  @Get('hot-leads-uncontacted')
  hotLeadsUncontacted(
    @TenantId() tenantId: string,
    @Query() query: HotLeadsQueryDto,
  ) {
    return this.dashboardService.hotLeadsUncontacted(tenantId, query);
  }
}
