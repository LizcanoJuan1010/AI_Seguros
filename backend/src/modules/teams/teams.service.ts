import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateTeamDto, QueryTeamsDto, UpdateTeamDto } from './teams.dto';

@Injectable()
export class TeamsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateTeamDto) {
    return this.prisma.team.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryTeamsDto) {
    const where = {
      ...(query.managerId && { managerId: query.managerId }),
      ...(query.search && {
        name: { contains: query.search, mode: 'insensitive' as const },
      }),
    };
    const [data, total] = await Promise.all([
      this.prisma.team.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.team.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.team.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateTeamDto) {
    return this.prisma.team.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.team.delete({ where: { id } });
  }

  private toData(dto: CreateTeamDto): Prisma.TeamUncheckedCreateInput;
  private toData(dto: UpdateTeamDto): Prisma.TeamUncheckedUpdateInput;
  private toData(dto: CreateTeamDto | UpdateTeamDto): unknown {
    return dto;
  }
}
