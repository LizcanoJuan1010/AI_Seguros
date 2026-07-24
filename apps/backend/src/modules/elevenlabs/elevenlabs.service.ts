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

  async handlePostCallWebhook(body: Record<string, unknown>) {
    const type = body.type;
    if (type !== 'post_call_transcription') {
      // Otros tipos (p.ej. post_call_audio) se reconocen pero no procesamos
      // todavía: 200 igual, ElevenLabs solo reintenga si no hay 2xx.
      this.logger.debug(`Webhook ElevenLabs ignorado (type=${String(type)})`);
      return { received: true, processed: false };
    }

    const data = body.data as PostCallWebhookData | undefined;
    if (!data) {
      throw new BadRequestException('Payload de ElevenLabs sin campo "data"');
    }

    const dynamicVariables =
      data.conversation_initiation_client_data?.dynamic_variables ?? {};
    const phone = dynamicVariables.phone;
    if (typeof phone !== 'string' || !phone.trim()) {
      throw new BadRequestException(
        'dynamic_variables.phone es requerido para asociar la llamada a un cliente',
      );
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
    }

    return { received: true, processed: true, aiCallId: aiCall.id };
  }
}
