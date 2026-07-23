import 'dotenv/config';
import { defineConfig, env } from 'prisma/config';

export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: {
    path: 'prisma/migrations',
  },
  datasource: {
    // Los comandos de CLI (migrate, introspect) necesitan la conexión DIRECTA
    // de Supabase (puerto 5432). El pooler de transacciones (DATABASE_URL, 6543)
    // NO soporta migraciones y las cuelga. El cliente en runtime sigue usando
    // DATABASE_URL vía el adapter en PrismaService — esto no lo afecta.
    url: env('DIRECT_URL'),
  },
});
