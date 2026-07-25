import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Post,
  UseGuards,
} from '@nestjs/common';
import { ElevenLabsInitGuard } from './elevenlabs-init.guard';
import { ElevenLabsSignatureGuard } from './elevenlabs-signature.guard';
import { ElevenLabsService } from './elevenlabs.service';

// Guards a nivel de método, NO de clase: cada webhook de ElevenLabs tiene su
// propio mecanismo de auth (init = header simple, webhook post-call = firma
// HMAC), así que un guard de clase único ya no alcanza. Quien llama a ambos
// es ElevenLabs (un tercero real), nunca un usuario ni otro servicio interno.
@Controller('elevenlabs')
export class ElevenLabsController {
  constructor(private readonly service: ElevenLabsService) {}

  /**
   * Llamado por ElevenLabs al iniciar la llamada (hoy: llamadas entrantes de
   * Twilio, ver "Twilio personalization" en su doc) para pedir los datos de
   * inicialización de la conversación. Nunca debe fallar de cara a
   * ElevenLabs — si el lead no existe, el servicio responde con defaults.
   */
  @Post('init')
  @UseGuards(ElevenLabsInitGuard)
  @HttpCode(HttpStatus.OK)
  handleInit(@Body() body: Record<string, unknown>) {
    return this.service.handleInitWebhook(body);
  }

  /**
   * Recibe la transcripción al colgar. Responde 200 de inmediato y procesa
   * en background (idempotente por conversation_id) — ver
   * ElevenLabsService.handlePostCallWebhook.
   */
  @Post('webhook')
  @UseGuards(ElevenLabsSignatureGuard)
  @HttpCode(HttpStatus.OK)
  handleWebhook(@Body() body: Record<string, unknown>) {
    return this.service.handlePostCallWebhook(body);
  }
}
