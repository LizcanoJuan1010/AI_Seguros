import { Type } from 'class-transformer';
import {
  IsBoolean,
  IsEmail,
  IsEnum,
  IsISO8601,
  IsNotEmpty,
  IsNumber,
  IsObject,
  IsOptional,
  IsPositive,
  IsString,
  IsUUID,
  ValidateNested,
} from 'class-validator';
import { InsuranceType } from '../../generated/prisma/enums';

export class CheckoutCustomerDto {
  @IsString()
  @IsNotEmpty()
  fullName!: string;

  @IsOptional()
  @IsString()
  documentType?: string;

  @IsString()
  @IsNotEmpty()
  documentId!: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  birthDate?: string;

  @IsOptional()
  @IsEmail()
  email?: string;

  @IsOptional()
  @IsString()
  phone?: string;

  @IsOptional()
  @IsString()
  city?: string;

  @IsOptional()
  @IsString()
  department?: string;
}

export class CheckoutPaymentDto {
  @IsString()
  @IsNotEmpty()
  method!: string;

  @IsOptional()
  @IsString()
  reference?: string;
}

export class CheckoutDto {
  @ValidateNested()
  @Type(() => CheckoutCustomerDto)
  customer!: CheckoutCustomerDto;

  // Optional + validated in the service so the "habeas data" message is
  // returned for false, null and missing alike (consentData !== true → 400).
  @IsOptional()
  @IsBoolean()
  consentData?: boolean;

  @IsEnum(InsuranceType)
  insuranceType!: InsuranceType;

  @IsNumber()
  @IsPositive()
  monthlyPremiumCop!: number;

  @IsOptional()
  @IsObject()
  coverage?: Record<string, unknown>;

  @IsOptional()
  @ValidateNested()
  @Type(() => CheckoutPaymentDto)
  payment?: CheckoutPaymentDto;

  @IsOptional()
  @IsUUID('4')
  leadId?: string;
}
