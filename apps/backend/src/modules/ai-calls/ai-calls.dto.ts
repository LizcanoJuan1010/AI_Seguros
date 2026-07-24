import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsISO8601,
  IsNumberString,
  IsObject,
  IsOptional,
  IsString,
  IsUrl,
  IsUUID,
  Matches,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { CallStatus, LeadIntent } from '../../generated/prisma/enums';

export class CreateAiCallDto {
  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  @IsOptional()
  @IsEnum(CallStatus)
  status?: CallStatus;

  @IsOptional()
  @IsISO8601({ strict: true })
  startedAt?: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  endedAt?: string;

  @IsOptional()
  @IsUrl()
  recordingUrl?: string;

  @IsOptional()
  @IsString()
  summary?: string;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;

  @IsOptional()
  @IsNumberString()
  @Matches(/^(?:0(?:\.\d{1,2})?|1(?:\.0{1,2})?)$/)
  intentScore?: string;

  @IsOptional()
  @IsString()
  sentiment?: string;

  @IsOptional()
  @IsObject()
  metadata?: object;
}

export class UpdateAiCallDto extends PartialType(CreateAiCallDto) {}

export class QueryAiCallsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  @IsOptional()
  @IsEnum(CallStatus)
  status?: CallStatus;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;

  @IsOptional()
  @IsISO8601({ strict: true })
  from?: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  to?: string;
}
