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
import { CreateLeadDto, QueryLeadsDto, UpdateLeadDto } from './leads.dto';
import { LeadsService } from './leads.service';

@Controller('leads')
export class LeadsController {
  constructor(private readonly service: LeadsService) {}

  @Post()
  create(@Body() dto: CreateLeadDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryLeadsDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(@Param('id', UuidParamPipe) id: string, @Body() dto: UpdateLeadDto) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
