import { BadRequestException } from '@nestjs/common';
import { PrismaService } from '../../prisma/prisma.service';
import { CreatePolicyDto, QueryPoliciesDto } from './policies.dto';
import { PoliciesService } from './policies.service';

describe('PoliciesService', () => {
  const policy = {
    create: jest.fn(),
    findMany: jest.fn(),
    count: jest.fn(),
    findUnique: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
  };
  const prisma = { policy } as unknown as PrismaService;
  const service = new PoliciesService(prisma);

  const validDto: CreatePolicyDto = {
    quoteId: '11111111-1111-4111-8111-111111111111',
    customerId: '22222222-2222-4222-8222-222222222222',
    policyNumber: 'POL-001',
    startDate: '2026-01-01',
    endDate: '2027-01-01',
    monthlyPremiumCop: '95000.00',
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('rechaza una póliza cuyo fin no sea posterior al inicio', () => {
    expect(() =>
      service.create({
        ...validDto,
        endDate: validDto.startDate,
      }),
    ).toThrow(BadRequestException);
    expect(policy.create).not.toHaveBeenCalled();
  });

  it('crea una póliza convirtiendo fechas y prima', async () => {
    policy.create.mockResolvedValue({ id: 'policy-id' });

    await service.create(validDto);

    const [{ data }] = policy.create.mock.calls[0] as unknown as [
      {
        data: {
          startDate: Date;
          endDate: Date;
          monthlyPremiumCop: { toFixed(): string };
        };
      },
    ];
    expect(data.startDate).toEqual(new Date('2026-01-01'));
    expect(data.endDate).toEqual(new Date('2027-01-01'));
    expect(data.monthlyPremiumCop.toFixed()).toBe('95000');
  });

  it('pagina los resultados y devuelve metadatos', async () => {
    policy.findMany.mockResolvedValue([{ id: 'policy-id' }]);
    policy.count.mockResolvedValue(1);
    const query = Object.assign(new QueryPoliciesDto(), {
      page: 1,
      limit: 20,
      order: 'desc' as const,
    });

    await expect(service.findAll(query)).resolves.toEqual({
      data: [{ id: 'policy-id' }],
      meta: { page: 1, limit: 20, total: 1, totalPages: 1 },
    });
  });
});
