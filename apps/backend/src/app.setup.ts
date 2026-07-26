import { INestApplication, ValidationPipe } from '@nestjs/common';
import { PrismaExceptionFilter } from './common/filters/prisma-exception.filter';
import { DecimalSerializerInterceptor } from './common/interceptors/decimal-serializer.interceptor';

export function configureApp(app: INestApplication): void {
  app.setGlobalPrefix('api/v1');
  app.useGlobalPipes(
    new ValidationPipe({
      transform: true,
      whitelist: true,
      forbidNonWhitelisted: true,
    }),
  );
  // CORS_ORIGINS: mismo patrón que apps/ai (CORS_ORIGINS, coma-separado).
  // Con el proxy same-origin (nginx local o Railway) el navegador nunca
  // cruza origen, así que esto no debería activarse en ese caso — pero
  // deja la puerta abierta sin hardcodear el puerto del dev server.
  const corsOrigins = (process.env.CORS_ORIGINS ?? 'http://localhost:5173')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
  app.enableCors({
    origin: corsOrigins,
    credentials: true,
  });
  app.useGlobalFilters(new PrismaExceptionFilter());
  app.useGlobalInterceptors(new DecimalSerializerInterceptor());
}
