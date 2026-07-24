import { NestFactory } from '@nestjs/core';
import { WsAdapter } from '@nestjs/platform-ws';
import { AppModule } from './app.module';
import { configureApp } from './app.setup';

async function bootstrap() {
  // rawBody: true → Nest adjunta req.rawBody (Buffer) además de parsear JSON.
  // Lo necesitan dos verificaciones de firma sobre bytes crudos (no el JSON
  // re-serializado): ElevenLabsSignatureGuard (webhook post-call) y la firma
  // Standard Webhooks de Polar (payments.service verifySignature).
  const app = await NestFactory.create(AppModule, { rawBody: true });
  // WsAdapter (ws nativo) en vez del socket.io por defecto: LiveCallGateway
  // necesita relayar audio binario y frames JSON byte-a-byte, sin el
  // framing propio de socket.io.
  app.useWebSocketAdapter(new WsAdapter(app));
  configureApp(app);
  await app.listen(process.env.PORT ?? 3000);
}
void bootstrap();
