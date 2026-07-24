import {
  IsEnum,
  IsNotEmpty,
  IsNumber,
  IsOptional,
  IsPositive,
  IsString,
} from 'class-validator';
import { PaymentStatus } from '../../generated/prisma/enums';

/** Alta del pago: la envía el servicio IA al generar el link (status pending). */
export class CreatePaymentDto {
  @IsString()
  @IsNotEmpty()
  reference!: string;

  @IsOptional()
  @IsString()
  provider?: string;

  @IsOptional()
  @IsString()
  linkId?: string;

  @IsOptional()
  @IsString()
  checkoutUrl?: string;

  @IsNumber()
  @IsPositive()
  amountCop!: number;

  @IsOptional()
  @IsString()
  currency?: string;

  @IsOptional()
  @IsString()
  concept?: string;

  @IsOptional()
  @IsString()
  sessionKey?: string;
}

/** Actualización de estado: polling de verificar_pago y aclaraciones. */
export class UpdatePaymentDto {
  @IsOptional()
  @IsEnum(PaymentStatus)
  status?: PaymentStatus;

  @IsOptional()
  @IsString()
  transactionId?: string;

  @IsOptional()
  @IsString()
  method?: string;

  @IsOptional()
  @IsString()
  disputeReason?: string;
}
