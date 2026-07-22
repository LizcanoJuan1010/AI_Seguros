import { PartialType } from '@nestjs/mapped-types';
import {
  IsEnum,
  IsISO8601,
  IsNotEmpty,
  IsOptional,
  IsString,
  IsUUID,
} from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';
import { SpeakerType } from '../../generated/prisma/enums';

export class CreateCallMessageDto {
  @IsUUID('4')
  callId!: string;

  @IsEnum(SpeakerType)
  speaker!: SpeakerType;

  @IsString()
  @IsNotEmpty()
  content!: string;

  @IsOptional()
  @IsISO8601({ strict: true })
  spokenAt?: string;
}

export class UpdateCallMessageDto extends PartialType(CreateCallMessageDto) {}

export class QueryCallMessagesDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  callId?: string;

  @IsOptional()
  @IsEnum(SpeakerType)
  speaker?: SpeakerType;
}
