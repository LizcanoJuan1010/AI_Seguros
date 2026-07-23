import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsISO8601,
  IsNumberString,
  IsObject,
  IsOptional,
  IsUUID,
  Matches,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { QuoteStatus } from '../../generated/prisma/enums';

export class CreateQuoteDto {
  @IsUUID('4')
  leadId!: string;

  @IsUUID('4')
  productId!: string;

  @IsOptional()
  @IsUUID('4')
  createdBy?: string;

  @IsObject()
  coverage!: object;

  @IsNumberString()
  @Matches(/^\d+(?:\.\d+)?$/)
  monthlyPremiumCop!: string;

  @IsOptional()
  @IsEnum(QuoteStatus)
  status?: QuoteStatus;

  @IsOptional()
  @IsISO8601({ strict: true })
  validUntil?: string;
}

export class UpdateQuoteDto extends PartialType(CreateQuoteDto) {}

export class QueryQuotesDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  leadId?: string;

  @IsOptional()
  @IsUUID('4')
  productId?: string;

  @IsOptional()
  @IsEnum(QuoteStatus)
  status?: QuoteStatus;
}
