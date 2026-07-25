import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsOptional,
  IsString,
  MinLength,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import {
  CampaignChannel,
  CampaignSendStatus,
  InsuranceType,
  LeadIntent,
} from '../../generated/prisma/enums';

export class CreateCampaignDto {
  @IsString()
  @MinLength(1)
  phrase!: string;

  @IsOptional()
  @IsString()
  subtitle?: string;

  @IsOptional()
  @IsString()
  cta?: string;

  @IsOptional()
  @IsEnum(InsuranceType)
  insuranceType?: InsuranceType;

  @IsEnum(CampaignChannel)
  channel!: CampaignChannel;

  // URL devuelta por POST /api/marketing/banner (apps/ai) — el archivo real
  // vive en el servicio IA, acá solo se persiste la referencia.
  @IsOptional()
  @IsString()
  bannerUrl?: string;
}

export class UpdateCampaignDto extends PartialType(CreateCampaignDto) {}

export class QueryCampaignsDto extends PaginationQueryDto {
  @IsOptional()
  @IsEnum(CampaignChannel)
  channel?: CampaignChannel;
}

export class SendCampaignDto {
  @IsEnum(LeadIntent)
  intent!: LeadIntent;

  @IsString()
  @MinLength(1)
  message!: string;
}

// Callback interno del servicio IA (apps/ai/app/campaign_broadcast.py) tras
// intentar el envío de un CampaignSend puntual.
export class UpdateCampaignSendDto {
  @IsEnum(CampaignSendStatus)
  status!: CampaignSendStatus;

  @IsOptional()
  @IsString()
  error?: string;
}
