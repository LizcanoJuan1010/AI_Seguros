import { Module } from '@nestjs/common';
import { LeadEventsController } from './lead-events.controller';
import { LeadEventsService } from './lead-events.service';

@Module({ controllers: [LeadEventsController], providers: [LeadEventsService] })
export class LeadEventsModule {}
