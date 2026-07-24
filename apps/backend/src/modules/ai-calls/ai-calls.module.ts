import { Module } from '@nestjs/common';
import { CustomersModule } from '../customers/customers.module';
import { LeadsModule } from '../leads/leads.module';
import { AiCallsController } from './ai-calls.controller';
import { AiCallsService } from './ai-calls.service';

@Module({
  imports: [CustomersModule, LeadsModule],
  controllers: [AiCallsController],
  providers: [AiCallsService],
})
export class AiCallsModule {}
