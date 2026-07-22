import { Module } from '@nestjs/common';
import { JwtModule } from '@nestjs/jwt';
import { AuthController } from './auth.controller';
import { AuthService } from './auth.service';

/**
 * JwtModule se registra como `global` para que `JwtService` (verificación de
 * tokens) esté disponible en los guards aplicados a los controllers de dominio
 * sin tener que importarlo en cada módulo. Secret = `JWT_SECRET` (HS256).
 */
@Module({
  imports: [
    JwtModule.register({
      global: true,
      secret: process.env.JWT_SECRET,
    }),
  ],
  controllers: [AuthController],
  providers: [AuthService],
})
export class AuthModule {}
