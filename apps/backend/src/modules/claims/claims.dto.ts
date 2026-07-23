import { PartialType } from '@nestjs/mapped-types';
import {
  IsArray,
  IsEnum,
  IsISO8601,
  IsNumber,
  IsOptional,
  IsString,
  IsUUID,
  Max,
  Min,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { ClaimStatus, InsuranceType } from '../../generated/prisma/enums';

export class CreateClaimDto {
  @IsOptional()
  @IsUUID('4')
  policyId?: string;

  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  // Si no viene, el servicio genera CLM-YYYY-000NNN (mismo patrón de policies).
  @IsOptional()
  @IsString()
  claimNumber?: string;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsOptional()
  @IsEnum(ClaimStatus)
  status?: ClaimStatus;

  @IsOptional()
  @IsString()
  description?: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  incidentDate?: string;

  @IsOptional()
  @IsNumber()
  @Min(0)
  amountEstimateCop?: number;

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(1)
  fraudScore?: number;

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  fraudFlags?: string[];

  @IsOptional()
  @IsArray()
  @IsString({ each: true })
  documents?: string[];

  @IsOptional()
  @IsString()
  aiSummary?: string;
}

export class UpdateClaimDto extends PartialType(CreateClaimDto) {}

export class QueryClaimsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  policyId?: string;

  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  @IsOptional()
  @IsEnum(ClaimStatus)
  status?: ClaimStatus;
}
