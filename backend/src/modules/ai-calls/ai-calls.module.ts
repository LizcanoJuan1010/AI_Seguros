import { Module } from '@nestjs/common';
import { AiCallsController } from './ai-calls.controller';
import { AiCallsService } from './ai-calls.service';

@Module({ controllers: [AiCallsController], providers: [AiCallsService] })
export class AiCallsModule {}
