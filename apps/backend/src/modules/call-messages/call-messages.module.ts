import { Module } from '@nestjs/common';
import { CallMessagesController } from './call-messages.controller';
import { CallMessagesService } from './call-messages.service';

@Module({
  controllers: [CallMessagesController],
  providers: [CallMessagesService],
})
export class CallMessagesModule {}
