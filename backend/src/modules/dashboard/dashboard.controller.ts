import { Controller, Get, Query } from '@nestjs/common';
import { AgentPerformanceQueryDto, HotLeadsQueryDto } from './dashboard.dto';
import { DashboardService } from './dashboard.service';

@Controller('dashboard')
export class DashboardController {
  constructor(private readonly dashboardService: DashboardService) {}

  @Get('agent-performance')
  agentPerformance(@Query() query: AgentPerformanceQueryDto) {
    return this.dashboardService.agentPerformance(query);
  }

  @Get('daily-kpis')
  dailyKpis() {
    return this.dashboardService.dailyKpis();
  }

  @Get('hot-leads-uncontacted')
  hotLeadsUncontacted(@Query() query: HotLeadsQueryDto) {
    return this.dashboardService.hotLeadsUncontacted(query);
  }
}
