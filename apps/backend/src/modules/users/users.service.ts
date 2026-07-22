import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateUserDto, QueryUsersDto, UpdateUserDto } from './users.dto';

@Injectable()
export class UsersService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateUserDto) {
    return this.prisma.user.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryUsersDto) {
    const where = {
      ...(query.teamId && { teamId: query.teamId }),
      ...(query.role && { role: query.role }),
      ...(query.status && { status: query.status }),
      ...(query.search && {
        OR: [
          {
            fullName: { contains: query.search, mode: 'insensitive' as const },
          },
          { email: { contains: query.search, mode: 'insensitive' as const } },
        ],
      }),
    };
    const [data, total] = await Promise.all([
      this.prisma.user.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.user.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.user.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateUserDto) {
    return this.prisma.user.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.user.delete({ where: { id } });
  }

  private toData(dto: CreateUserDto): Prisma.UserUncheckedCreateInput;
  private toData(dto: UpdateUserDto): Prisma.UserUncheckedUpdateInput;
  private toData(dto: CreateUserDto | UpdateUserDto): unknown {
    return dto;
  }
}
