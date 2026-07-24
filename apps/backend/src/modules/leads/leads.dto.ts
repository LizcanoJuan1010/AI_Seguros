import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsISO8601,
  IsObject,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import {
  InsuranceType,
  LeadIntent,
  LeadStatus,
} from '../../generated/prisma/enums';

export class CreateLeadDto {
  @IsUUID('4')
  customerId!: string;

  @IsOptional()
  @IsUUID('4')
  aiCallId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsOptional()
  @IsEnum(LeadStatus)
  status?: LeadStatus;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;

  @IsOptional()
  @IsISO8601({ strict: true })
  assignedAt?: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  firstContactAt?: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  closedAt?: string;

  @IsOptional()
  @IsString()
  lostReason?: string;

  @IsOptional()
  @IsObject()
  aiNextSteps?: object;
}

export class UpdateLeadDto extends PartialType(CreateLeadDto) {}

export class QueryLeadsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsOptional()
  @IsEnum(LeadStatus)
  status?: LeadStatus;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;
}

export class QueryLeadsQueueDto extends PaginationQueryDto {
  // Sin agentId = vista de manager (todo el equipo); con agentId = cola de
  // ese agente puntual.
  @IsOptional()
  @IsUUID('4')
  agentId?: string;
}

export class UpsertLeadDto {
  @IsString()
  phone!: string;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsOptional()
  @IsEnum(LeadStatus)
  status?: LeadStatus;
}
