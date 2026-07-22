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
import { CreateUserDto, QueryUsersDto, UpdateUserDto } from './users.dto';
import { UsersService } from './users.service';

@Controller('users')
export class UsersController {
  constructor(private readonly service: UsersService) {}

  @Post()
  create(@Body() dto: CreateUserDto) {
    return this.service.create(dto);
  }

  @Get()
  findAll(@Query() query: QueryUsersDto) {
    return this.service.findAll(query);
  }

  @Get(':id')
  findOne(@Param('id', UuidParamPipe) id: string) {
    return this.service.findOne(id);
  }

  @Patch(':id')
  update(@Param('id', UuidParamPipe) id: string, @Body() dto: UpdateUserDto) {
    return this.service.update(id, dto);
  }

  @Delete(':id')
  @HttpCode(HttpStatus.NO_CONTENT)
  async remove(@Param('id', UuidParamPipe) id: string): Promise<void> {
    await this.service.remove(id);
  }
}
