import { Type } from 'class-transformer';
import {
  IsBoolean,
  IsEnum,
  IsInt,
  IsOptional,
  IsUUID,
  Min,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { LeadIntent, LeadStatus } from '../../generated/prisma/enums';

export class AgentPerformanceQueryDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  teamId?: string;
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
