import { Module } from '@nestjs/common';
import { LeadsModule } from '../leads/leads.module';
import { LeadEventsController } from './lead-events.controller';
import { LeadEventsService } from './lead-events.service';

@Module({
  imports: [LeadsModule],
  controllers: [LeadEventsController],
  providers: [LeadEventsService],
})
export class LeadEventsModule {}
