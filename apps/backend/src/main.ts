import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { configureApp } from './app.setup';

async function bootstrap() {
  // rawBody: la firma Standard Webhooks de Polar se calcula sobre el cuerpo
  // crudo del request (payments.service verifySignature).
  const app = await NestFactory.create(AppModule, { rawBody: true });
  configureApp(app);
  await app.listen(process.env.PORT ?? 3000);
}
void bootstrap();
