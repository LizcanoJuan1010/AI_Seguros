-- Alinea ai_calls como registro multicanal (whatsapp/email/web_chat/voice_call)
-- y le da tenant scoping igual que customers/leads/quotes/policies.
-- Idempotente (IF EXISTS / IF NOT EXISTS / bloque DO para el enum).

-- 1) Enum de canal ---------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE channel AS ENUM ('whatsapp', 'email', 'web_chat', 'voice_call');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 2) Columnas team_id + channel en ai_calls --------------------------------
ALTER TABLE ai_calls ADD COLUMN IF NOT EXISTS team_id UUID;
ALTER TABLE ai_calls ADD COLUMN IF NOT EXISTS channel channel NOT NULL DEFAULT 'whatsapp';

-- 3) Foreign key a teams(id) ------------------------------------------------
ALTER TABLE ai_calls DROP CONSTRAINT IF EXISTS ai_calls_team_id_fkey;
ALTER TABLE ai_calls
    ADD CONSTRAINT ai_calls_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

-- 4) Índice por tenant ------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_ai_calls_team ON ai_calls(team_id);
