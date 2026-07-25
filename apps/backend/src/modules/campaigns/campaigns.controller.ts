import { Body, Controller, Get, Param, Patch, Post, Query, UseGuards } from '@nestjs/common';
import { JwtAuthGuard, OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { UuidParamPipe } from '../../common/pipes/uuid-param.pipe';
import { Roles } from '../../common/roles.decorator';
import { RolesGuard } from '../../common/roles.guard';
import { TenantId } from '../../common/tenant.decorator';
import {
  CreateCampaignDto,
  QueryCampaignsDto,
  SendCampaignDto,
  UpdateCampaignSendDto,
} from './campaigns.dto';
import { CampaignsService } from './campaigns.service';

// Guards a nivel de MÉTODO (no de controller): todo lo gerencial exige
// JwtAuthGuard+RolesGuard, salvo el callback interno de apps/ai al final,
// que solo necesita OptionalJwtAuthGuard (tráfico servicio-a-servicio, mismo
// criterio que /leads/upsert y /call-messages).
@Controller('campaigns')
export class CampaignsController {
  constructor(private readonly service: CampaignsService) {}

  @Post()
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('GERENTE', 'ADMIN')
  create(@TenantId() tenantId: string, @Body() dto: CreateCampaignDto) {
    return this.service.create(tenantId, dto);
  }

  @Get()
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('GERENTE', 'ADMIN')
  findAll(@TenantId() tenantId: string, @Query() query: QueryCampaignsDto) {
    return this.service.findAll(tenantId, query);
  }

  @Get(':id')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('GERENTE', 'ADMIN')
  findOne(@TenantId() tenantId: string, @Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(tenantId, id);
  }

  @Get(':id/sends-summary')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('GERENTE', 'ADMIN')
  sendsSummary(@TenantId() tenantId: string, @Param('id', UuidParamPipe) id: string) {
    return this.service.sendsSummary(tenantId, id);
  }

  @Post(':id/send')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('GERENTE', 'ADMIN')
  send(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: SendCampaignDto,
  ) {
    return this.service.send(tenantId, id, dto);
  }

  @Patch('sends/:sendId')
  @UseGuards(OptionalJwtAuthGuard)
  updateSendStatus(
    @Param('sendId', UuidParamPipe) sendId: string,
    @Body() dto: UpdateCampaignSendDto,
  ) {
    return this.service.updateSendStatus(sendId, dto);
  }
}
