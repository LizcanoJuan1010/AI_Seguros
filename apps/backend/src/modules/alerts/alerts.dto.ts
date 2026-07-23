import { PartialType } from '@nestjs/mapped-types';
import { Transform, type TransformFnParams } from 'class-transformer';
import {
  IsBoolean,
  IsIn,
  IsISO8601,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';

function parseBoolean({ value }: TransformFnParams): unknown {
  if (value === 'true') return true;
  if (value === 'false') return false;
  return value as unknown;
}

export class CreateAlertDto {
  @IsOptional()
  @IsUUID('4')
  teamId?: string;

  @IsOptional()
  @IsUUID('4')
  leadId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsString()
  @IsNotEmpty()
  message!: string;

  @IsOptional()
  @IsIn(['baja', 'media', 'alta'])
  severity?: 'baja' | 'media' | 'alta';

  @IsOptional()
  @IsBoolean()
  resolved?: boolean;

  @IsOptional()
  @IsISO8601({ strict: true })
  resolvedAt?: string;
}

export class UpdateAlertDto extends PartialType(CreateAlertDto) {}

export class QueryAlertsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  teamId?: string;

  @IsOptional()
  @IsUUID('4')
  leadId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @Transform(parseBoolean)
  @IsBoolean()
  resolved?: boolean;

  @IsOptional()
  @IsIn(['baja', 'media', 'alta'])
  severity?: 'baja' | 'media' | 'alta';
}
