import { Module } from '@nestjs/common';
import { ConfigModule, ConfigService } from '@nestjs/config';
import { JwtModule } from '@nestjs/jwt';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';

/**
 * JwtModule se registra como `global` para que `JwtService` (verificación de
 * tokens) esté disponible en los guards aplicados a los controllers de dominio
 * sin tener que importarlo en cada módulo. Secret = `JWT_SECRET` (HS256).
 *
 * Se usa `registerAsync` para leer el secret DESPUÉS de que ConfigModule
 * cargue el `.env` (un `process.env.JWT_SECRET` en el decorador queda vacío).
 */
@Module({
  imports: [
    JwtModule.registerAsync({
      global: true,
      imports: [ConfigModule],
      inject: [ConfigService],
      useFactory: (config: ConfigService) => {
        const secret = config.get<string>('JWT_SECRET');
        if (!secret) {
          throw new Error(
            'JWT_SECRET no está definido. Agrégalo en apps/backend/.env',
          );
        }
        return { secret };
      },
    }),
  ],
  controllers: [AuthController],
  providers: [AuthService],
})
export class AuthModule {}
