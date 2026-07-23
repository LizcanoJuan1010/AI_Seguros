import { BadRequestException, Injectable, Logger } from '@nestjs/common';
import { resolveTenantId } from '../../common/tenant.decorator';
import { CallStatus, Channel, SpeakerType } from '../../generated/prisma/enums';
import { Prisma } from '../../generated/prisma/client';
import { PrismaService } from '../../prisma/prisma.service';
import { CustomersService } from '../customers/customers.service';

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
  ) {}

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

    return { received: true, processed: true, aiCallId: aiCall.id };
  }
}
