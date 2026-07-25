-- Adquisición del cliente: red social / canal de origen y el link por el que
-- llegó a la aplicación. Alimenta la métrica "redes con mayor adquisición" del
-- panel del gerente. Idempotente (IF NOT EXISTS) como el resto.

ALTER TABLE customers ADD COLUMN IF NOT EXISTS referral_source TEXT;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS referral_link TEXT;

-- Índice para agrupar por fuente (KPI de adquisición por red social).
CREATE INDEX IF NOT EXISTS idx_customers_referral_source
  ON customers(team_id, referral_source);
