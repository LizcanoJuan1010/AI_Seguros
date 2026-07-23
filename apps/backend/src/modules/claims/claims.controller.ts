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
import { CreateClaimDto, QueryClaimsDto, UpdateClaimDto } from './claims.dto';
import { ClaimsService } from './claims.service';

@UseGuards(OptionalJwtAuthGuard)
@Controller('claims')
export class ClaimsController {
  constructor(private readonly service: ClaimsService) {}

  @Post()
  create(@TenantId() tenantId: string, @Body() dto: CreateClaimDto) {
    return this.service.create(tenantId, dto);
  }

  @Get()
  findAll(@TenantId() tenantId: string, @Query() query: QueryClaimsDto) {
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
    @Body() dto: UpdateClaimDto,
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
