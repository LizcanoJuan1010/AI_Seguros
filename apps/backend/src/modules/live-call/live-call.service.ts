import { Injectable } from '@nestjs/common';
import { CallStatus, Channel, SpeakerType } from '../../generated/prisma/enums';
import { AiCallsService } from '../ai-calls/ai-calls.service';
import { CallMessagesService } from '../call-messages/call-messages.service';

/**
 * Lado Postgres de la llamada en vivo: abrir sesión, persistir turnos y
 * cerrar el AiCall. Sin WebSockets acá — eso vive en live-call.gateway.ts,
 * que llama a estos métodos al "espiar" transcript_final/turn_end (ver
 * design.md, decisión "Nest turn persistence hook").
 */
@Injectable()
export class LiveCallService {
  constructor(
    private readonly aiCalls: AiCallsService,
    private readonly callMessages: CallMessagesService,
  ) {}

  /**
   * Abre (o reutiliza, vía la regla de sesión de AiCallsService.openSession)
   * el AiCall del canal WEB_VOICE_CALL. `userSub` es el `sub` del JWT — la
   * llamada en vivo es un widget del dashboard, no un cliente por WhatsApp,
   * así que no hay un teléfono real: se sintetiza uno estable por usuario
   * (mismo patrón que `user_id = f"web:{session_id}"` en assistant.py).
   */
  async openSession(tenantId: string, userSub: string): Promise<string> {
    const { id } = await this.aiCalls.openSession(tenantId, {
      phone: `web:${userSub}`,
      channel: Channel.WEB_VOICE_CALL,
    });
    return id;
  }

  recordClientTurn(tenantId: string, aiCallId: string, content: string) {
    return this.callMessages.create(tenantId, {
      callId: aiCallId,
      speaker: SpeakerType.CLIENTE,
      content,
    });
  }

  recordAssistantTurn(tenantId: string, aiCallId: string, content: string) {
    return this.callMessages.create(tenantId, {
      callId: aiCallId,
      speaker: SpeakerType.IA,
      content,
    });
  }

  finalizeCall(tenantId: string, aiCallId: string, status: CallStatus) {
    return this.aiCalls.update(tenantId, aiCallId, {
      status,
      endedAt: new Date().toISOString(),
    });
  }
}
