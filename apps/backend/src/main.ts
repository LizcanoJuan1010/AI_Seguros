import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { configureApp } from './app.setup';

async function bootstrap() {
  // rawBody: true → Nest adjunta req.rawBody (Buffer) además de parsear JSON.
  // Lo necesitan dos verificaciones de firma sobre bytes crudos (no el JSON
  // re-serializado): ElevenLabsSignatureGuard (webhook post-call) y la firma
  // Standard Webhooks de Polar (payments.service verifySignature).
  const app = await NestFactory.create(AppModule, { rawBody: true });
  configureApp(app);
  await app.listen(process.env.PORT ?? 3000);
}
void bootstrap();
