import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateCustomerDto,
  QueryCustomersDto,
  UpdateCustomerDto,
} from './customers.dto';

@Injectable()
export class CustomersService {
  constructor(private readonly prisma: PrismaService) {}

  create(tenantId: string, dto: CreateCustomerDto) {
    return this.prisma.customer.create({
      data: { ...this.toData(dto), teamId: tenantId },
    });
  }

  async findAll(tenantId: string, query: QueryCustomersDto) {
    const where = {
      teamId: tenantId,
      ...(query.city && {
        city: { equals: query.city, mode: 'insensitive' as const },
      }),
      ...(query.documentId && { documentId: query.documentId }),
      ...(query.search && {
        OR: [
          {
            fullName: { contains: query.search, mode: 'insensitive' as const },
          },
          { email: { contains: query.search, mode: 'insensitive' as const } },
          { phone: { contains: query.search } },
        ],
      }),
    };
    const [data, total] = await Promise.all([
      this.prisma.customer.findMany({
        where,
        ...paginationArgs(query.page, query.limit),
        orderBy: { createdAt: query.order },
      }),
      this.prisma.customer.count({ where }),
    ]);
    return paginated(data, total, query.page, query.limit);
  }

  findOne(tenantId: string, id: string) {
    return this.prisma.customer.findFirstOrThrow({
      where: { id, teamId: tenantId },
    });
  }

  /**
   * Resuelve un Customer por teléfono dentro del tenant, creándolo si no
   * existe. Lo usan integraciones que solo conocen el teléfono del cliente
   * (webhook de ElevenLabs, canal WhatsApp/web vía el servicio IA) y no un id.
   */
  async findOrCreateByPhone(tenantId: string, phone: string) {
    const existing = await this.prisma.customer.findFirst({
      where: { teamId: tenantId, phone },
    });
    if (existing) return existing;
    return this.prisma.customer.create({
      data: { teamId: tenantId, phone },
    });
  }

  async update(tenantId: string, id: string, dto: UpdateCustomerDto) {
    await this.findOne(tenantId, id);
    return this.prisma.customer.update({
      where: { id },
      data: this.toData(dto),
    });
  }

  async remove(tenantId: string, id: string): Promise<void> {
    await this.findOne(tenantId, id);
    await this.prisma.customer.delete({ where: { id } });
  }

  private toData(dto: CreateCustomerDto): Prisma.CustomerUncheckedCreateInput;
  private toData(dto: UpdateCustomerDto): Prisma.CustomerUncheckedUpdateInput;
  private toData(dto: CreateCustomerDto | UpdateCustomerDto): unknown {
    const consentAt =
      dto.consentData === false
        ? null
        : dto.consentAt
          ? new Date(dto.consentAt)
          : dto.consentData === true
            ? new Date()
            : undefined;

    return {
      ...dto,
      ...(dto.birthDate !== undefined && {
        birthDate: new Date(dto.birthDate),
      }),
      ...(consentAt !== undefined && { consentAt }),
    };
  }
}
