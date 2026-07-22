import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import { CreateQuoteDto, QueryQuotesDto, UpdateQuoteDto } from './quotes.dto';

@Injectable()
export class QuotesService {
  constructor(private readonly prisma: PrismaService) {}

  create(dto: CreateQuoteDto) {
    return this.prisma.quote.create({ data: this.toData(dto) });
  }

  async findAll(query: QueryQuotesDto) {
    const where = {
      ...(query.leadId && { leadId: query.leadId }),
      ...(query.productId && { productId: query.productId }),
      ...(query.status && { status: query.status }),
    };
    const [data, total] = await Promise.all([
      this.prisma.quote.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.quote.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(id: string) {
    return this.prisma.quote.findUniqueOrThrow({ where: { id } });
  }

  async update(id: string, dto: UpdateQuoteDto) {
    return this.prisma.quote.update({ where: { id }, data: this.toData(dto) });
  }

  async remove(id: string): Promise<void> {
    await this.prisma.quote.delete({ where: { id } });
  }

  private toData(dto: CreateQuoteDto): Prisma.QuoteUncheckedCreateInput;
  private toData(dto: UpdateQuoteDto): Prisma.QuoteUncheckedUpdateInput;
  private toData(dto: CreateQuoteDto | UpdateQuoteDto): unknown {
    const { coverage, monthlyPremiumCop, validUntil, ...rest } = dto;
    return {
      ...rest,
      ...(coverage !== undefined && {
        coverage: coverage as Prisma.InputJsonValue,
      }),
      ...(monthlyPremiumCop !== undefined && {
        monthlyPremiumCop: new Prisma.Decimal(monthlyPremiumCop),
      }),
      ...(validUntil !== undefined && { validUntil: new Date(validUntil) }),
    };
  }
}
