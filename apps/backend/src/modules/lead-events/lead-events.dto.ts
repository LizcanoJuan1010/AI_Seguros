import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { EventType } from '../../generated/prisma/enums';

export class CreateLeadEventDto {
  @IsUUID('4')
  leadId!: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsEnum(EventType)
  eventType!: EventType;

  @IsOptional()
  @IsString()
  notes?: string;

  @IsOptional()
  @IsObject()
  payload?: object;
}

export class UpdateLeadEventDto extends PartialType(CreateLeadEventDto) {}

export class QueryLeadEventsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  leadId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @IsEnum(EventType)
  eventType?: EventType;
}
