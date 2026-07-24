import {
  Body,
  Controller,
  Delete,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { UuidParamPipe } from '../../common/pipes/uuid-param.pipe';
import { TenantId } from '../../common/tenant.decorator';
import { LeadScoringService } from './lead-scoring.service';
import {
  CreateLeadDto,
  QueryLeadsDto,
  QueryLeadsQueueDto,
  UpdateLeadDto,
  UpsertLeadDto,
} from './leads.dto';
import { LeadsService } from './leads.service';

@UseGuards(OptionalJwtAuthGuard)
@Controller('leads')
export class LeadsController {
  constructor(
    private readonly service: LeadsService,
    private readonly leadScoring: LeadScoringService,
  ) {}

  @Post()
  create(@TenantId() tenantId: string, @Body() dto: CreateLeadDto) {
    return this.service.create(tenantId, dto);
  }

  // La usa el servicio IA (Python, cotizador) para resolver/crear el Lead de
  // un teléfono sin conocer un customerId. Debe ir antes de rutas ':id'.
  @Post('upsert')
  upsert(@TenantId() tenantId: string, @Body() dto: UpsertLeadDto) {
    return this.service.upsertByPhone(tenantId, dto);
  }

  // La cola priorizada. Debe declararse antes de `@Get(':id')` — si no, Nest
  // interpreta "queue" como un :id.
  @Get('queue')
  findQueue(@TenantId() tenantId: string, @Query() query: QueryLeadsQueueDto) {
    return this.service.findQueue(tenantId, query);
  }

  @Get()
  findAll(@TenantId() tenantId: string, @Query() query: QueryLeadsDto) {
    return this.service.findAll(tenantId, query);
  }

  @Get(':id')
  findOne(@TenantId() tenantId: string, @Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(tenantId, id);
  }

  // Recalcular a mano (debug / futuro botón "recalcular ahora"). Confirma
  // primero que el lead es del tenant antes de recomputar.
  @Post(':id/recompute')
  @HttpCode(HttpStatus.OK)
  async recompute(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
  ) {
    const lead = await this.service.findOne(tenantId, id);
    await this.leadScoring.recomputeOne(lead.id);
    return this.service.findOne(tenantId, id);
  }

  @Patch(':id')
  update(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: UpdateLeadDto,
  ) {
    return this.service.update(tenantId, id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
  ): Promise<void> {
    await this.service.remove(tenantId, id);
  }
}
