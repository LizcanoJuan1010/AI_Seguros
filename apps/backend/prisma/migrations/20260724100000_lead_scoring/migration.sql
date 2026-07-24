-- Motor de leads: progresión de canal (click/interés -> WhatsApp -> llamada)
-- y clusterización por velocidad de respuesta (frío/tibio/caliente dinámico).
-- Idempotente (IF EXISTS / IF NOT EXISTS / bloque DO para el valor de enum).

-- 1) Nuevo valor de canal: click/interés previo a cualquier conversación real.
DO $$ BEGIN
    ALTER TYPE channel ADD VALUE IF NOT EXISTS 'web_interest';
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2) Columnas nuevas en leads ------------------------------------------------
ALTER TABLE leads ADD COLUMN IF NOT EXISTS first_channel channel;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS highest_channel channel;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_customer_response_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS last_outbound_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS priority_score INTEGER NOT NULL DEFAULT 0;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS priority_score_updated_at TIMESTAMPTZ;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS intent_override lead_intent;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS intent_override_at TIMESTAMPTZ;

-- 3) Índice para la cola priorizada (GET /leads/queue) ----------------------
CREATE INDEX IF NOT EXISTS idx_leads_queue ON leads(team_id, status, priority_score DESC);
