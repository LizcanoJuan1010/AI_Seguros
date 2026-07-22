import { PartialType } from '@nestjs/mapped-types';
import { IsNotEmpty, IsOptional, IsString, IsUUID } from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';

export class CreateTeamDto {
  @IsString()
  @IsNotEmpty()
  name!: string;

  @IsOptional()
  @IsUUID('4')
  managerId?: string;
}

export class UpdateTeamDto extends PartialType(CreateTeamDto) {}

export class QueryTeamsDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  managerId?: string;

  @IsOptional()
  @IsString()
  search?: string;
}
