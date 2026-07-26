import { Module } from '@nestjs/common';
import { AiCallsModule } from '../ai-calls/ai-calls.module';
import { CallMessagesModule } from '../call-messages/call-messages.module';
import { LiveCallGateway } from './live-call.gateway';
import { LiveCallService } from './live-call.service';

@Module({
  imports: [AiCallsModule, CallMessagesModule],
  providers: [LiveCallGateway, LiveCallService],
})
export class LiveCallModule {}
