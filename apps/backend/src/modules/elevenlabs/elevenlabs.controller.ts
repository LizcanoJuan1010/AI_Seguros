import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Post,
  UseGuards,
} from '@nestjs/common';
import { ElevenLabsSignatureGuard } from './elevenlabs-signature.guard';
import { ElevenLabsService } from './elevenlabs.service';

// Sin @UseGuards(OptionalJwtAuthGuard): quien llama es ElevenLabs (un tercero
// real), no un usuario ni otro servicio interno — se autentica solo con la
// firma HMAC de ElevenLabsSignatureGuard.
@UseGuards(ElevenLabsSignatureGuard)
@Controller('elevenlabs')
export class ElevenLabsController {
  constructor(private readonly service: ElevenLabsService) {}

  @Post('webhook')
  @HttpCode(HttpStatus.OK)
  handleWebhook(@Body() body: Record<string, unknown>) {
    return this.service.handlePostCallWebhook(body);
  }
}
