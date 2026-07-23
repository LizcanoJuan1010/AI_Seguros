import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { AiCallsModule } from './modules/ai-calls/ai-calls.module';
import { AlertsModule } from './modules/alerts/alerts.module';
import { AuthModule } from './modules/auth/auth.module';
import { CallMessagesModule } from './modules/call-messages/call-messages.module';
import { CheckoutModule } from './modules/checkout/checkout.module';
import { CustomersModule } from './modules/customers/customers.module';
import { DashboardModule } from './modules/dashboard/dashboard.module';
import { LeadEventsModule } from './modules/lead-events/lead-events.module';
import { LeadsModule } from './modules/leads/leads.module';
import { PaymentsModule } from './modules/payments/payments.module';
import { PoliciesModule } from './modules/policies/policies.module';
import { ProductsModule } from './modules/products/products.module';
import { QuotesModule } from './modules/quotes/quotes.module';
import { TeamsModule } from './modules/teams/teams.module';
import { UsersModule } from './modules/users/users.module';
import { PrismaModule } from './prisma/prisma.module';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env', '../.env', '../../.env'],
    }),
    PrismaModule,
    AuthModule,
    TeamsModule,
    UsersModule,
    CustomersModule,
    ProductsModule,
    AiCallsModule,
    CallMessagesModule,
    LeadsModule,
    LeadEventsModule,
    QuotesModule,
    PoliciesModule,
    AlertsModule,
    DashboardModule,
    CheckoutModule,
    PaymentsModule,
  ],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule {}
