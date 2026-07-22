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
  CreateCallMessageDto,
  QueryCallMessagesDto,
  UpdateCallMessageDto,
} from './call-messages.dto';
import { CallMessagesService } from './call-messages.service';

@Controller('call-messages')
export class CallMessagesController {
  constructor(private readonly service: CallMessagesService) {}

  @Post()
  create(@Body() dto: CreateCallMessageDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryCallMessagesDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(
    @Param('id', UuidParamPipe) id: string,
    @Body() dto: UpdateCallMessageDto,
  ) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
