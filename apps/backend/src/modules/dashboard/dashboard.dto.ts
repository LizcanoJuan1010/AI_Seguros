import { Type } from 'class-transformer';
import {
  IsBoolean,
  IsEnum,
  IsIn,
  IsInt,
  IsOptional,
  IsString,
  IsUUID,
  MaxLength,
  Min,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import {
  InsuranceType,
  LeadIntent,
  LeadStatus,
} from '../../generated/prisma/enums';

/** Nivel de riesgo agregado por cliente (ver DashboardService.customerPortfolio). */
export const RISK_LEVELS = ['alto', 'medio', 'bajo'] as const;
export type RiskLevel = (typeof RISK_LEVELS)[number];

export class AgentPerformanceQueryDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  teamId?: string;
}

export class CustomerPortfolioQueryDto extends PaginationQueryDto {
  // Busca por nombre, teléfono, email o documento del cliente.
  @IsOptional()
  @IsString()
  @MaxLength(120)
  search?: string;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;

  @IsOptional()
  @IsEnum(LeadStatus)
  status?: LeadStatus;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsOptional()
  @IsIn(RISK_LEVELS)
  risk?: RiskLevel;
}

export class HotLeadsQueryDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @IsBoolean()
  @Type(() => Boolean)
  unassignedOnly?: boolean;

  @IsOptional()
  @IsEnum(LeadIntent)
  intent?: LeadIntent;

  @IsOptional()
  @IsEnum(LeadStatus)
  status?: LeadStatus;

  // Horas sin primer contacto para contar como "caliente sin atender".
  // Antes era un valor fijo (2h) en la vista SQL v_hot_leads_uncontacted.
  @IsOptional()
  @Type(() => Number)
  @IsInt()
  @Min(0)
  staleHours?: number;
}
