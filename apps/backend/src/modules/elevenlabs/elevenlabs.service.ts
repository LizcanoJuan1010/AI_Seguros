import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { resolveTenantId } from '../../common/tenant.decorator';
import { CallStatus, Channel, SpeakerType } from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { PrismaService } from '../../prisma/prisma.service';
import { CustomersService } from '../customers/customers.service';
import { LeadScoringService } from '../leads/lead-scoring.service';
import { LeadsService } from '../leads/leads.service';

interface TranscriptTurn {
  role?: string;
  message?: string | null;
  time_in_call_secs?: number;
}

interface InitWebhookRequest {
  caller_id?: string;
  agent_id?: string;
  called_number?: string;
  call_sid?: string;
}

// Fila cruda de seguria.intake_session (schema Python, MISMA base de
// Postgres) — `datos` es el intake crudo (dependientes, tenencia, placa,
// marca, modelo_anio, actividad_economica, nombre_completo...) que
// agent_core.py arma turno a turno vía guardar_datos_cliente. OJO: NO es lo
// mismo que seguria.customer_profile.perfil (ese es un RESUMEN derivado —
// edad/segmento_riesgo/etc, ya no trae los campos crudos) — se probó en
// vivo y confirmado que perfil no los conserva.
interface IntakeSessionRow {
  datos: Record<string, unknown> | null;
}

interface PostCallWebhookData {
  conversation_id?: string;
  agent_id?: string;
  agent_name?: string;
  status?: string;
  transcript?: TranscriptTurn[];
  metadata?: {
    start_time_unix_secs?: number;
    call_duration_secs?: number;
    termination_reason?: string;
  };
  analysis?: {
    transcript_summary?: string;
    call_successful?: string;
  };
  conversation_initiation_client_data?: {
    dynamic_variables?: Record<string, unknown>;
  };
}

// Motivos de terminación que ElevenLabs puede reportar como fallidos/abandonados.
// La lista exacta no está fijada en su doc pública; se mapea por palabras clave
// y cualquier caso no reconocido cae en COMPLETADA si hubo transcript, o
// FALLIDA si la llamada no llegó a tener contenido.
function mapCallStatus(data: PostCallWebhookData): CallStatus {
  const reason = (data.metadata?.termination_reason ?? '').toLowerCase();
  if (reason.includes('transfer')) return CallStatus.TRANSFERIDA_HUMANO;
  if (reason.includes('abandon') || reason.includes('no_answer') || reason.includes('no-answer')) {
    return CallStatus.ABANDONADA;
  }
  if (reason.includes('error') || reason.includes('fail')) return CallStatus.FALLIDA;
  if ((data.transcript?.length ?? 0) === 0) return CallStatus.FALLIDA;
  return CallStatus.COMPLETADA;
}

function mapSpeaker(role: string | undefined): SpeakerType {
  return role === 'agent' ? SpeakerType.IA : SpeakerType.CLIENTE;
}

function edadDesdeFecha(fecha: string | undefined): number | null {
  if (!fecha) return null;
  const nacimiento = new Date(fecha);
  if (Number.isNaN(nacimiento.getTime())) return null;
  const hoy = new Date();
  let edad = hoy.getFullYear() - nacimiento.getFullYear();
  const noHaCumplidoEsteAño =
    hoy.getMonth() < nacimiento.getMonth() ||
    (hoy.getMonth() === nacimiento.getMonth() && hoy.getDate() < nacimiento.getDate());
  if (noHaCumplidoEsteAño) edad -= 1;
  return edad;
}

// Defaults — el webhook de init NUNCA debe fallar de cara a ElevenLabs
// (documentado: si el lead no existe, se responde con estos valores).
const DYNAMIC_VARIABLE_DEFAULTS: Record<string, string | number> = {
  nombre: 'cliente',
  edad: 0,
  afiliacion: 'no disponible',
  dependientes: 0,
  vivienda: 'no disponible',
  vehiculo: 'sin vehículo registrado',
  tipo_ingreso: 'no disponible',
  productos_vigentes: 'ninguno',
};

@Injectable()
export class ElevenLabsService {
  private readonly logger = new Logger(ElevenLabsService.name);

  constructor(
    private readonly prisma: PrismaService,
    private readonly customers: CustomersService,
    private readonly leads: LeadsService,
    private readonly leadScoring: LeadScoringService,
    private readonly config: ConfigService,
  ) {}

  /**
   * Perfilamiento post-llamada: le pasa el transcript completo al servicio
   * IA (Python) para que extraiga datos del cliente por LLM y construya el
   * perfil (mismo `profiling.build_profile` que usa el chat de WhatsApp/web,
   * ver apps/ai/app/call_profiling.py). Primera llamada NestJS->Python del
   * sistema — hasta ahora todo iba en la dirección contraria. Fire-and-forget
   * con `fetch` nativo (Node 20+): no bloquea la respuesta al webhook de
   * ElevenLabs ni falla el registro de la llamada si el servicio IA no responde.
   */
  private notifyCallProfiling(
    tenantId: string,
    phone: string,
    transcript: TranscriptTurn[],
  ): void {
    const baseUrl = this.config.get<string>('AI_SERVICE_URL') ?? 'http://seguria-ai:8085';
    const serviceKey = this.config.get<string>('SERVICE_API_KEY') ?? 'demo-service-2026';
    fetch(`${baseUrl}/api/profiling/from-call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Service-Key': serviceKey },
      body: JSON.stringify({ phone, tenant_id: tenantId, transcript }),
    }).catch((err: unknown) =>
      this.logger.warn(`no se pudo disparar el perfilamiento post-llamada: ${String(err)}`),
    );
  }

  /**
   * Alimenta el motor de versionado/QA de prompts (docket, adaptado de
   * docket-motor — ver apps/ai/app/docket_engine/) con el transcript real de
   * la llamada, para que cluster.py/judge.py/optimize.py puedan medir y
   * mejorar el prompt de Tequendama con datos reales. Mismo patrón
   * fire-and-forget que `notifyCallProfiling`: nunca bloquea ni rompe el
   * registro de la llamada si el servicio IA no responde o el motor está
   * apagado (DOCKET_ENGINE_ENABLED=false del lado de apps/ai).
   */
  private notifyDocketMotor(conversationId: string | null, transcript: TranscriptTurn[]): void {
    const baseUrl = this.config.get<string>('AI_SERVICE_URL') ?? 'http://seguria-ai:8085';
    const serviceKey = this.config.get<string>('SERVICE_API_KEY') ?? 'demo-service-2026';
    fetch(`${baseUrl}/api/docket/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Service-Key': serviceKey },
      body: JSON.stringify({ conversation_id: conversationId, transcript }),
    }).catch((err: unknown) =>
      this.logger.warn(`no se pudo sincronizar la llamada hacia docket: ${String(err)}`),
    );
  }

  /**
   * Webhook de inicio de llamada (POST /elevenlabs/init). Busca al lead por
   * `caller_id` (E.164) y arma `dynamic_variables`. NUNCA lanza un error de
   * cara a ElevenLabs — cualquier fallo (DB caída, lead no encontrado, dato
   * parcial) cae a los defaults; el try/catch envuelve TODO el método.
   *
   * Mapeo (los nombres pedidos no existen 1:1 en ningún modelo — ver nota):
   *   nombre             <- Customer.fullName
   *   edad               <- Customer.birthDate (o perfil.fecha_nacimiento)
   *   afiliacion         <- perfil.afiliado_colsubsidio (Sí/No -> texto)
   *   dependientes       <- perfil.dependientes (match exacto)
   *   vivienda           <- perfil.tenencia (propietario/arrendatario)
   *   vehiculo           <- perfil.marca + modelo_anio si tiene placa
   *   tipo_ingreso       <- perfil.actividad_economica
   *   productos_vigentes <- pólizas VIGENTE del customer, nombres de producto
   * `perfil` viene de `seguria.intake_session.datos` (schema de Python,
   * MISMA base — el intake crudo que agent_core.py arma turno a turno),
   * buscado por `session_key LIKE '%:' || callerId` (session_key =
   * "{tenant_id}:{phone}", el tenant no se conoce desde solo el caller_id).
   * Ajusta este mapeo si tu intención real era otra.
   */
  async handleInitWebhook(body: InitWebhookRequest) {
    const fallback = {
      type: 'conversation_initiation_client_data',
      dynamic_variables: { ...DYNAMIC_VARIABLE_DEFAULTS },
    };

    try {
      const callerId = body.caller_id?.trim();
      if (!callerId) return fallback;

      const customer = await this.prisma.customer.findFirst({
        where: { phone: callerId },
      });

      const suffix = `:${callerId}`;
      const intakeRows = await this.prisma.$queryRaw<IntakeSessionRow[]>`
        SELECT datos::jsonb AS datos FROM seguria.intake_session
        WHERE session_key LIKE ${'%' + suffix} ORDER BY updated_at DESC LIMIT 1
      `;
      const perfil = intakeRows[0]?.datos ?? {};

      let productosVigentes = DYNAMIC_VARIABLE_DEFAULTS.productos_vigentes;
      if (customer) {
        const polizas = await this.prisma.policy.findMany({
          where: { customerId: customer.id, status: 'VIGENTE' },
          include: { quote: { include: { product: true } } },
        });
        if (polizas.length) {
          productosVigentes = polizas.map((p) => p.quote.product.name).join(', ');
        }
      }

      const tieneVehiculo = Boolean(perfil.placa);
      const dynamic_variables = {
        nombre: customer?.fullName || (perfil.nombre_completo as string) || DYNAMIC_VARIABLE_DEFAULTS.nombre,
        edad:
          edadDesdeFecha(customer?.birthDate?.toISOString()) ??
          edadDesdeFecha(perfil.fecha_nacimiento as string | undefined) ??
          DYNAMIC_VARIABLE_DEFAULTS.edad,
        afiliacion:
          perfil.afiliado_colsubsidio === true
            ? 'afiliado'
            : perfil.afiliado_colsubsidio === false
              ? 'no afiliado'
              : DYNAMIC_VARIABLE_DEFAULTS.afiliacion,
        dependientes: (perfil.dependientes as number) ?? DYNAMIC_VARIABLE_DEFAULTS.dependientes,
        vivienda: (perfil.tenencia as string) || DYNAMIC_VARIABLE_DEFAULTS.vivienda,
        vehiculo: tieneVehiculo
          ? `${perfil.marca ?? ''} ${perfil.modelo_anio ?? ''}`.trim()
          : DYNAMIC_VARIABLE_DEFAULTS.vehiculo,
        tipo_ingreso: (perfil.actividad_economica as string) || DYNAMIC_VARIABLE_DEFAULTS.tipo_ingreso,
        productos_vigentes: productosVigentes,
      };

      return { type: 'conversation_initiation_client_data', dynamic_variables };
    } catch (err) {
      this.logger.warn(`init webhook: fallo buscando el lead, uso defaults: ${String(err)}`);
      return fallback;
    }
  }

  /**
   * Recibe la transcripción al colgar. Responde 200 DE INMEDIATO (antes de
   * procesar nada pesado) e idempotente por `conversation_id` — si ya existe
   * un AiCall con ese conversation_id, no reprocesa (ElevenLabs puede
   * reintentar el mismo webhook). El procesamiento real corre en background
   * (fire-and-forget, sin await) para no bloquear la respuesta a ElevenLabs.
   */
  async handlePostCallWebhook(body: Record<string, unknown>) {
    const type = body.type;
    if (type !== 'post_call_transcription') {
      // Otros tipos (post_call_audio, call_initiation_failure) se reconocen
      // pero no se procesan todavía: 200 igual, ElevenLabs solo reintenta
      // si no hay 2xx.
      this.logger.debug(`Webhook ElevenLabs ignorado (type=${String(type)})`);
      return { received: true, processed: false };
    }

    const data = body.data as PostCallWebhookData | undefined;
    if (!data) {
      throw new BadRequestException('Payload de ElevenLabs sin campo "data"');
    }

    const conversationId = data.conversation_id ?? null;
    if (conversationId) {
      const existing = await this.prisma.aiCall.findFirst({
        where: { metadata: { path: ['conversationId'], equals: conversationId } },
        select: { id: true },
      });
      if (existing) {
        this.logger.log(`webhook duplicado (conversation_id=${conversationId}), ya procesado — ignorado`);
        return { received: true, processed: false, duplicate: true };
      }
    }

    // Fire-and-forget a propósito: ElevenLabs solo necesita el 200, el
    // registro real (Customer/Lead/AiCall/transcript/scoring/profiling) no
    // debe demorar esa respuesta.
    this.processTranscription(data).catch((err: unknown) =>
      this.logger.error(`error procesando webhook post-call en background: ${String(err)}`),
    );

    return { received: true, processed: true };
  }

  private async processTranscription(data: PostCallWebhookData): Promise<void> {
    const dynamicVariables =
      data.conversation_initiation_client_data?.dynamic_variables ?? {};
    const phone = dynamicVariables.phone;
    if (typeof phone !== 'string' || !phone.trim()) {
      this.logger.warn('post-call webhook sin dynamic_variables.phone — no se puede asociar a un cliente');
      return;
    }
    const tenantId = resolveTenantId(dynamicVariables.tenant_id);

    const customer = await this.customers.findOrCreateByPhone(
      tenantId,
      phone.trim(),
    );
    // Primer contacto real (o escalación a llamada de un lead ya existente).
    await this.leads.findOrCreateOpenLead(tenantId, customer.id, Channel.VOICE_CALL);

    const startedAt = data.metadata?.start_time_unix_secs
      ? new Date(data.metadata.start_time_unix_secs * 1000)
      : new Date();
    const durationSec = data.metadata?.call_duration_secs ?? null;
    const endedAt = durationSec
      ? new Date(startedAt.getTime() + durationSec * 1000)
      : null;

    const aiCall = await this.prisma.aiCall.create({
      data: {
        teamId: tenantId,
        customerId: customer.id,
        channel: Channel.VOICE_CALL,
        status: mapCallStatus(data),
        startedAt,
        endedAt,
        // durationSec NO se envía: es una columna GENERATED ALWAYS AS
        // (ended_at - started_at) STORED en Postgres — insertarla explícito
        // rompe con "cannot insert a non-DEFAULT value into column".
        summary: data.analysis?.transcript_summary,
        metadata: {
          conversationId: data.conversation_id ?? null,
          agentId: data.agent_id ?? null,
          agentName: data.agent_name ?? null,
          callSuccessful: data.analysis?.call_successful ?? null,
          terminationReason: data.metadata?.termination_reason ?? null,
          dynamicVariables,
        } as Prisma.InputJsonValue,
      },
    });

    const transcript = data.transcript ?? [];
    if (transcript.length) {
      await this.prisma.callMessage.createMany({
        data: transcript.map((turn, index) => ({
          callId: aiCall.id,
          speaker: mapSpeaker(turn.role),
          content: turn.message ?? '',
          spokenAt: new Date(
            startedAt.getTime() + (turn.time_in_call_secs ?? index) * 1000,
          ),
        })),
      });
    }

    // Este flujo usa createMany directo (no CallMessagesService), así que el
    // recálculo de scoring no se dispara solo — se llama explícito aquí.
    this.leadScoring
      .recomputeForCustomer(tenantId, customer.id)
      .catch(() => undefined);

    if (transcript.length) {
      this.notifyCallProfiling(tenantId, phone.trim(), transcript);
      this.notifyDocketMotor(data.conversation_id ?? null, transcript);
    }
  }
}
