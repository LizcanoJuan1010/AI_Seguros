import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateProductDto,
  QueryProductsDto,
  UpdateProductDto,
} from './products.dto';

@Injectable()
export class ProductsService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateProductDto) {
    return this.prisma.product.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryProductsDto) {
    const where = {
      ...(query.insuranceType && { insuranceType: query.insuranceType }),
      ...(query.isActive !== undefined && { isActive: query.isActive }),
      ...(query.search && {
        name: { contains: query.search, mode: 'insensitive' as const },
      }),
    };
    const [data, total] = await Promise.all([
      this.prisma.product.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.product.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.product.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateProductDto) {
    return this.prisma.product.update({
      where: { id },
      data: this.toData(dto),
    });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.product.delete({ where: { id } });
  }

  private toData(dto: CreateProductDto): Prisma.ProductUncheckedCreateInput;
  private toData(dto: UpdateProductDto): Prisma.ProductUncheckedUpdateInput;
  private toData(dto: CreateProductDto | UpdateProductDto): unknown {
    const { basePremiumCop, coverageSchema, ...rest } = dto;
    return {
      ...rest,
      ...(basePremiumCop !== undefined && {
        basePremiumCop: new Prisma.Decimal(basePremiumCop),
      }),
      ...(coverageSchema !== undefined && {
        coverageSchema: coverageSchema as Prisma.InputJsonValue,
      }),
    };
  }
}
