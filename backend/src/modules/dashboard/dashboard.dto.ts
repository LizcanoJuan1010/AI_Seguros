import { IsOptional, IsUUID } from 'class-validator';
import { PaginationQueryDto } from '../../common/dto/pagination-query.dto';

export class AgentPerformanceQueryDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  teamId?: string;
}

export class HotLeadsQueryDto extends PaginationQueryDto {
  @IsOptional()
  @IsUUID('4')
  agentId?: string;
}
