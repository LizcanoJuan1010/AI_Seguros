import { PartialType } from '@nestjs/mapped-types';
import { IsEnum, IsOptional, IsString, MinLength } from 'class-validator';
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

// Interacción con la publicación de esta Campaign (like/comentario/clic) ANTES
// de cualquier conversación real — ver docs/PLAN_CORRETAJE_ASEGURADORAS.md §3.2.
// Quien identifica al interesado (aún no resuelto, ver §5.3 del plan) manda el
// teléfono que haya podido capturar; el resto (crear/resolver Lead, marcar
// `interesInicial`, loguear el evento) lo hace `CampaignsService.registerInterest`.
export class RegisterInterestDto {
  @IsString()
  @MinLength(1)
  phone!: string;

  @IsOptional()
  @IsString()
  fullName?: string;
}
