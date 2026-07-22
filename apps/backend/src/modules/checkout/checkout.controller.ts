import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Post,
  UseGuards,
} from '@nestjs/common';
import { OptionalJwtAuthGuard } from '../../common/jwt-auth.guard';
import { TenantId } from '../../common/tenant.decorator';
import { CheckoutDto } from './checkout.dto';
import { CheckoutService } from './checkout.service';

@UseGuards(OptionalJwtAuthGuard)
@Controller('checkout')
export class CheckoutController {
  constructor(private readonly service: CheckoutService) {}

  @Post()
  @HttpCode(HttpStatus.CREATED)
  checkout(@TenantId() tenantId: string, @Body() dto: CheckoutDto) {
    return this.service.checkout(tenantId, dto);
  }
}
