import { Module } from '@nestjs/common';
import { LeadsModule } from '../leads/leads.module';
import { CallMessagesController } from './call-messages.controller';
import { CallMessagesService } from './call-messages.service';

@Module({
  imports: [LeadsModule],
  controllers: [CallMessagesController],
  providers: [CallMessagesService],
})
export class CallMessagesModule {}
