-- Conecta el "primer contacto" por redes sociales (Campaign) con Lead — ver
-- docs/PLAN_CORRETAJE_ASEGURADORAS.md §3.2. Idempotente (IF NOT EXISTS /
-- DO $$ ... $$), mismo patrón que las migraciones anteriores.

-- 1) EventType: nuevo valor para "interacción con una publicación/campaña,
--    antes de cualquier conversación real" -----------------------------------
DO $$ BEGIN
    ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'interes_social';
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- 2) leads.interes_inicial: categoría de interés capturada en el primer
--    contacto (distinta de insurance_type, que es lo YA cotizado) -----------
ALTER TABLE leads ADD COLUMN IF NOT EXISTS interes_inicial insurance_type;

-- 3) lead_events.campaign_id: qué Campaign disparó el evento ----------------
ALTER TABLE lead_events ADD COLUMN IF NOT EXISTS campaign_id UUID;
ALTER TABLE lead_events DROP CONSTRAINT IF EXISTS lead_events_campaign_id_fkey;
ALTER TABLE lead_events
    ADD CONSTRAINT lead_events_campaign_id_fkey
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_lead_events_campaign ON lead_events(campaign_id);
