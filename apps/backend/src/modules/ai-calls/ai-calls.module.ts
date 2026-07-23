import { Module } from '@nestjs/common';
import { CustomersModule } from '../customers/customers.module';
import { AiCallsController } from './ai-calls.controller';
import { AiCallsService } from './ai-calls.service';

@Module({
  imports: [CustomersModule],
  controllers: [AiCallsController],
  providers: [AiCallsService],
})
export class AiCallsModule {}
