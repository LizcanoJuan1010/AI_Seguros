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
} from '@nestjs/common';
import { UuidParamPipe } from '../../common/pipes/uuid-param.pipe';
import {
  CreatePolicyDto,
  QueryPoliciesDto,
  UpdatePolicyDto,
} from './policies.dto';
import { PoliciesService } from './policies.service';

@Controller('policies')
export class PoliciesController {
  constructor(private readonly service: PoliciesService) {}

  @Post()
  create(@Body() dto: CreatePolicyDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryPoliciesDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(@Param('id', UuidParamPipe) id: string, @Body() dto: UpdatePolicyDto) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
