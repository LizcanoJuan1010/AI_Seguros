import { Module } from '@nestjs/common';
import { CustomersModule } from '../customers/customers.module';
import { LeadsModule } from '../leads/leads.module';
import { ElevenLabsController } from './elevenlabs.controller';
import { ElevenLabsInitGuard } from './elevenlabs-init.guard';
import { ElevenLabsSignatureGuard } from './elevenlabs-signature.guard';
import { ElevenLabsService } from './elevenlabs.service';

@Module({
  imports: [CustomersModule, LeadsModule],
  controllers: [ElevenLabsController],
  providers: [ElevenLabsService, ElevenLabsSignatureGuard, ElevenLabsInitGuard],
})
export class ElevenLabsModule {}
