import { Module } from '@nestjs/common';
import { CustomersModule } from '../customers/customers.module';
import { LeadScoringConfigService } from './lead-scoring.config';
import { LeadScoringService } from './lead-scoring.service';
import { LeadsController } from './leads.controller';
import { LeadsService } from './leads.service';

@Module({
  imports: [CustomersModule],
  controllers: [LeadsController],
  providers: [LeadsService, LeadScoringConfigService, LeadScoringService],
  exports: [LeadsService, LeadScoringService],
})
export class LeadsModule {}
