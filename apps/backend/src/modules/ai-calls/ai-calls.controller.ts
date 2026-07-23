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
import {
  CreateAiCallDto,
  OpenSessionDto,
  QueryAiCallsDto,
  UpdateAiCallDto,
} from './ai-calls.dto';
import { AiCallsService } from './ai-calls.service';

@UseGuards(OptionalJwtAuthGuard)
@Controller('ai-calls')
export class AiCallsController {
  constructor(private readonly service: AiCallsService) {}

  // La usa el servicio IA (Python) para WhatsApp/web chat: resuelve/crea el
  // Customer por teléfono y reutiliza o abre la AiCall de ese canal.
  @Post('sessions')
  openSession(@TenantId() tenantId: string, @Body() dto: OpenSessionDto) {
    return this.service.openSession(tenantId, dto);
  }

  @Post()
  create(@TenantId() tenantId: string, @Body() dto: CreateAiCallDto) {
    return this.service.create(tenantId, dto);
  }

  @Get()
  findAll(@TenantId() tenantId: string, @Query() query: QueryAiCallsDto) {
    return this.service.findAll(tenantId, query);
  }

  @Get(':id')
  findOne(@TenantId() tenantId: string, @Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(tenantId, id);
  }

  @Patch(':id')
  update(
    @TenantId() tenantId: string,
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: UpdateAiCallDto,
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
