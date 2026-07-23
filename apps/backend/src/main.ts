import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { configureApp } from './app.setup';

async function bootstrap() {
  // rawBody: true → Nest adjunta req.rawBody (Buffer) además de parsear JSON.
  // Lo necesita ElevenLabsSignatureGuard: la firma HMAC se calcula sobre los
  // bytes crudos del body, no sobre el JSON re-serializado.
  const app = await NestFactory.create(AppModule, { rawBody: true });
  configureApp(app);
  await app.listen(process.env.PORT ?? 3000);
}
void bootstrap();
