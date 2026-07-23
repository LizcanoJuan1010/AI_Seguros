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
  CreateLeadEventDto,
  QueryLeadEventsDto,
  UpdateLeadEventDto,
} from './lead-events.dto';
import { LeadEventsService } from './lead-events.service';

@Controller('lead-events')
export class LeadEventsController {
  constructor(private readonly service: LeadEventsService) {}

  @Post()
  create(@Body() dto: CreateLeadEventDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryLeadEventsDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: UpdateLeadEventDto,
  ) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
