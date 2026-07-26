-- Campañas de marketing (banners generados con Gemini, ver
-- apps/ai/app/marketing_studio.py) + su rastro de envío segmentado por
-- intent de lead (CampaignSend). Idempotente (IF NOT EXISTS / DO $$ ... $$)
-- como el resto de migraciones.

-- 1) Enums --------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_channel') THEN
        CREATE TYPE campaign_channel AS ENUM
            ('instagram_post', 'instagram_story', 'linkedin', 'email');
    END IF;
END
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_send_status') THEN
        CREATE TYPE campaign_send_status AS ENUM
            ('pendiente', 'enviado', 'fallido', 'omitido');
    END IF;
END
$$;

-- 2) Tabla campaigns ------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaigns (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id        UUID,
    phrase         TEXT NOT NULL,
    subtitle       TEXT,
    cta            TEXT,
    insurance_type insurance_type,
    channel        campaign_channel NOT NULL,
    banner_url     TEXT,
    created_at     TIMESTAMPTZ(6) NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);

ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_team_id_fkey;
ALTER TABLE campaigns
    ADD CONSTRAINT campaigns_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_campaigns_team ON campaigns(team_id);

-- 3) Tabla campaign_sends ---------------------------------------------------
CREATE TABLE IF NOT EXISTS campaign_sends (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL,
    lead_id     UUID,
    customer_id UUID,
    intent      lead_intent,
    status      campaign_send_status NOT NULL DEFAULT 'pendiente',
    error       TEXT,
    sent_at     TIMESTAMPTZ(6),
    created_at  TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);

ALTER TABLE campaign_sends DROP CONSTRAINT IF EXISTS campaign_sends_campaign_id_fkey;
ALTER TABLE campaign_sends
    ADD CONSTRAINT campaign_sends_campaign_id_fkey
    FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE;

ALTER TABLE campaign_sends DROP CONSTRAINT IF EXISTS campaign_sends_lead_id_fkey;
ALTER TABLE campaign_sends
    ADD CONSTRAINT campaign_sends_lead_id_fkey
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE SET NULL;

ALTER TABLE campaign_sends DROP CONSTRAINT IF EXISTS campaign_sends_customer_id_fkey;
ALTER TABLE campaign_sends
    ADD CONSTRAINT campaign_sends_customer_id_fkey
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS campaign_sends_campaign_id_lead_id_key
    ON campaign_sends(campaign_id, lead_id);
CREATE INDEX IF NOT EXISTS idx_campaign_sends_campaign ON campaign_sends(campaign_id);
CREATE INDEX IF NOT EXISTS idx_campaign_sends_status ON campaign_sends(status, created_at);
