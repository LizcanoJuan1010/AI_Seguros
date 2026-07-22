import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsISO8601,
  IsNotEmpty,
  IsNumberString,
  IsOptional,
  IsString,
  IsUUID,
  Matches,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { PolicyStatus } from '../../generated/prisma/enums';

export class CreatePolicyDto {
  @IsUUID('4')
  quoteId!: string;

  @IsUUID('4')
  customerId!: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsString()
  @IsNotEmpty()
  policyNumber!: string;

  @IsOptional()
  @IsEnum(PolicyStatus)
  status?: PolicyStatus;

  @IsISO8601({ strict: true })
  startDate!: string;

  @IsISO8601({ strict: true })
  endDate!: string;

  @IsNumberString()
  @Matches(/^\d+(?:\.\d+)?$/)
  monthlyPremiumCop!: string;
}

export class UpdatePolicyDto extends PartialType(CreatePolicyDto) {}

export class QueryPoliciesDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  customerId?: string;

  @IsOptional()
  @IsUUID('4')
  agentId?: string;

  @IsOptional()
  @IsEnum(PolicyStatus)
  status?: PolicyStatus;
}
