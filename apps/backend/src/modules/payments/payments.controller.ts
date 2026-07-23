import {
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Param,
  Patch,
  Post,
  UseGuards,
} from '@nestjs/common';
import { OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { TenantId } from '../../common/tenant.decorator';
import { CreatePaymentDto, UpdatePaymentDto } from './payments.dto';
import { PaymentsService } from './payments.service';

@Controller('payments')
export class PaymentsController {
  constructor(private readonly service: PaymentsService) {}

  /**
   * Webhook de eventos de Wompi (transaction.updated). Público a propósito:
   * la autenticidad se valida con el checksum firmado (WOMPI_EVENTS_SECRET)
   * dentro del service, y siempre responde 200 para cortar los reintentos.
   * URL a registrar en el dashboard de Wompi: https://<host>/api/v1/payments/webhook
   */
  @Post('webhook')
  @HttpCode(HttpStatus.OK)
  webhook(@Body() event: Record<string, unknown>) {
    return this.service.handleWebhook(event);
  }

  @UseGuards(OptionalJwtAuthGuard)
  @Post()
  @HttpCode(HttpStatus.CREATED)
  create(@TenantId() tenantId: string, @Body() dto: CreatePaymentDto) {
    return this.service.create(tenantId, dto);
  }

  @UseGuards(OptionalJwtAuthGuard)
  @Get(':reference')
  get(@Param('reference') reference: string) {
    return this.service.get(reference);
  }

  @UseGuards(OptionalJwtAuthGuard)
  @Patch(':reference')
  update(
    @Param('reference') reference: string,
    @Body() dto: UpdatePaymentDto,
  ) {
    return this.service.update(reference, dto);
  }
}
