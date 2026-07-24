import { Injectable } from '@nestjs/common';
import { Prisma } from '../../generated/prisma/client';
import { paginated, paginationArgs } from '../../common/pagination';
import { PrismaService } from '../../prisma/prisma.service';
import {
  CreateCustomerDto,
  QueryCustomersDto,
  UpdateCustomerDto,
} from './customers.dto';

/** Perfil calculado por el servicio IA (seguria.customer_profile). */
interface AiProfileRow {
  perfil: unknown;
  fuente: string | null;
  updated_at: Date;
}

/** Datos declarados en la conversación (seguria.intake_session). */
interface IntakeRow {
  datos: unknown;
  updated_at: Date;
}

/** Turno de la conversación cliente↔IA (seguria.conversations). */
interface ConversationRow {
  role: string;
  message: string;
  channel: string | null;
  created_at: Date;
}

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
   * Cliente 360: agrega en una sola respuesta todo lo que el sistema conoce
   * del cliente. Del dominio (public): leads con su historial de eventos,
   * cotizaciones con producto, pólizas, reclamos y sesiones IA con
   * transcripción. Del servicio IA (esquema seguria, mismo Postgres): el
   * perfil calculado (etapa de vida, dependientes, riesgo, propensión,
   * necesidades) y los datos declarados en la conversación (ocupación,
   * ingresos, estado civil, beneficiarios...). Los bloques del esquema
   * seguria degradan a null si la tabla no existe o el teléfono no cruza.
   */
  async findFull(tenantId: string, id: string) {
    const customer = await this.findOne(tenantId, id);

    const [leads, quotes, policies, claims, aiCalls] = await Promise.all([
      this.prisma.lead.findMany({
        where: { customerId: id, teamId: tenantId },
        orderBy: { createdAt: 'desc' },
        include: {
          agent: { select: { fullName: true } },
          events: {
            orderBy: { createdAt: 'desc' },
            take: 30,
            include: { agent: { select: { fullName: true } } },
          },
        },
      }),
      this.prisma.quote.findMany({
        where: { teamId: tenantId, lead: { customerId: id } },
        orderBy: { createdAt: 'desc' },
        include: { product: { select: { name: true, insuranceType: true } } },
      }),
      this.prisma.policy.findMany({
        where: { customerId: id, teamId: tenantId },
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.claim.findMany({
        where: { customerId: id, teamId: tenantId },
        orderBy: { createdAt: 'desc' },
      }),
      this.prisma.aiCall.findMany({
        where: { customerId: id },
        orderBy: { startedAt: 'desc' },
        take: 10,
        include: { messages: { orderBy: { spokenAt: 'asc' } } },
      }),
    ]);

    // El cruce con el esquema seguria es por teléfono normalizado (últimos 10
    // dígitos): el perfil se guarda por phone y el intake por session_key
    // "{tenant}:{phone}".
    let aiProfile: { perfil: unknown; fuente: string | null; updatedAt: Date } | null =
      null;
    let intake: { datos: unknown; updatedAt: Date } | null = null;
    let conversation: {
      role: string;
      message: string;
      channel: string | null;
      createdAt: Date;
    }[] = [];
    const digits = customer.phone?.replace(/\D/g, '').slice(-10);
    if (digits && digits.length >= 7) {
      try {
        const [p] = await this.prisma.$queryRaw<AiProfileRow[]>(Prisma.sql`
          SELECT perfil, fuente, updated_at
          FROM seguria.customer_profile
          WHERE RIGHT(regexp_replace(phone, '\\D', '', 'g'), 10) = ${digits}
          ORDER BY updated_at DESC
          LIMIT 1
        `);
        if (p) {
          aiProfile = { perfil: p.perfil, fuente: p.fuente, updatedAt: p.updated_at };
        }
      } catch {
        // esquema seguria no disponible
      }
      try {
        const [s] = await this.prisma.$queryRaw<IntakeRow[]>(Prisma.sql`
          SELECT datos, updated_at
          FROM seguria.intake_session
          WHERE RIGHT(regexp_replace(session_key, '\\D', '', 'g'), 10) = ${digits}
          ORDER BY updated_at DESC
          LIMIT 1
        `);
        if (s) {
          // La columna seguria.intake_session.datos es TEXT (no JSONB): el
          // servicio IA guarda el JSON serializado. Se parsea aquí para que
          // la API siempre entregue un objeto.
          let datos: unknown = s.datos;
          if (typeof datos === 'string') {
            try {
              datos = JSON.parse(datos);
            } catch {
              datos = null;
            }
          }
          if (datos) intake = { datos, updatedAt: s.updated_at };
        }
      } catch {
        // esquema seguria no disponible
      }
      try {
        // El chat cliente↔IA (web/WhatsApp) vive en seguria.conversations
        // por teléfono. Se traen los turnos visibles (cliente y asistente)
        // en orden cronológico para el visor del drawer.
        const rows = await this.prisma.$queryRaw<ConversationRow[]>(Prisma.sql`
          SELECT role, message, channel, created_at
          FROM seguria.conversations
          WHERE RIGHT(regexp_replace(phone, '\\D', '', 'g'), 10) = ${digits}
            AND role IN ('cliente', 'asistente')
          ORDER BY created_at ASC
          LIMIT 200
        `);
        conversation = rows.map((r) => ({
          role: r.role,
          message: r.message,
          channel: r.channel,
          createdAt: r.created_at,
        }));
      } catch {
        // esquema seguria no disponible
      }
    }

    const edad = customer.birthDate
      ? Math.floor(
          (Date.now() - customer.birthDate.getTime()) / (365.25 * 86_400_000),
        )
      : null;

    return {
      customer: { ...customer, edad },
      aiProfile,
      intake,
      conversation,
      leads: leads.map(({ agent, events, ...lead }) => ({
        ...lead,
        agentName: agent?.fullName ?? null,
        events: events.map(({ agent: evAgent, ...ev }) => ({
          ...ev,
          agentName: evAgent?.fullName ?? null,
        })),
      })),
      quotes,
      policies,
      claims,
      aiCalls,
    };
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
