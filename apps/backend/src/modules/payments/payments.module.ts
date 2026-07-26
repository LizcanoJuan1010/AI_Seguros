import { Module } from '@nestjs/common';
import { PaymentsController } from './payments.controller';
import { PaymentsService } from './payments.service';
import { PolarClient } from './polar.client';

@Module({
  controllers: [PaymentsController],
  providers: [PaymentsService, PolarClient],
  exports: [PaymentsService, PolarClient],
})
export class PaymentsModule {}
