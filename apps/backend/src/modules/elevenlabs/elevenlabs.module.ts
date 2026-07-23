import { Module } from '@nestjs/common';
import { CustomersModule } from '../customers/customers.module';
import { ElevenLabsController } from './elevenlabs.controller';
import { ElevenLabsSignatureGuard } from './elevenlabs-signature.guard';
import { ElevenLabsService } from './elevenlabs.service';

@Module({
  imports: [CustomersModule],
  controllers: [ElevenLabsController],
  providers: [ElevenLabsService, ElevenLabsSignatureGuard],
})
export class ElevenLabsModule {}
