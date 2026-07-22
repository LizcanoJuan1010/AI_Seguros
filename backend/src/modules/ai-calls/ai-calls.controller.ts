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
  CreateAiCallDto,
  QueryAiCallsDto,
  UpdateAiCallDto,
} from './ai-calls.dto';
import { AiCallsService } from './ai-calls.service';

@Controller('ai-calls')
export class AiCallsController {
  constructor(private readonly service: AiCallsService) {}

  @Post()
  create(@Body() dto: CreateAiCallDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryAiCallsDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(@Param('id', UuidParamPipe) id: string, @Body() dto: UpdateAiCallDto) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
