-- Motor de versionado/QA de prompts (adaptado de docket-motor, bases 01-06)
-- reusando la misma base de Supabase, en un schema propio (`docket`) —
-- mismo patrón de separación por schema que ya existe con `seguria` (Python
-- crudo) vs `public` (Prisma). Prisma NO modela nada de este schema; es
-- propiedad exclusiva de apps/ai/app/docket_engine (SQL siempre
-- `docket.`-prefijado explícito, nunca depende de search_path).
-- Idempotente (IF NOT EXISTS en todo).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS docket;

CREATE TABLE IF NOT EXISTS docket.campaigns (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_slug TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- source_type suma 'app_sync' (turnos reales de Tequendama) a los 3 valores
-- originales de docket-motor (xlsx_row/zip_file/manual_upload, no usados acá).
CREATE TABLE IF NOT EXISTS docket.calls (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id  UUID NOT NULL REFERENCES docket.campaigns(id),
    external_id  TEXT,
    source_file  TEXT NOT NULL DEFAULT 'app_sync',
    source_type  TEXT NOT NULL DEFAULT 'app_sync'
                 CHECK (source_type IN ('xlsx_row', 'zip_file', 'manual_upload', 'app_sync')),
    transcript   TEXT,
    raw_meta     JSONB,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, source_file, external_id)
);
CREATE INDEX IF NOT EXISTS calls_campaign_id_idx ON docket.calls(campaign_id);

CREATE TABLE IF NOT EXISTS docket.clusters (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id         UUID NOT NULL REFERENCES docket.campaigns(id),
    representative_text TEXT NOT NULL,
    size                INTEGER NOT NULL DEFAULT 0,
    avg_pitch_std_hz    NUMERIC,
    avg_energy_rms      NUMERIC,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS clusters_campaign_id_idx ON docket.clusters(campaign_id);

CREATE TABLE IF NOT EXISTS docket.call_turns (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id          UUID NOT NULL REFERENCES docket.calls(id),
    cluster_id       UUID REFERENCES docket.clusters(id),
    role             TEXT NOT NULL CHECK (role IN ('agent', 'customer')),
    turn_text        TEXT NOT NULL,
    start_seconds    NUMERIC,
    end_seconds      NUMERIC,
    pitch_mean_hz    NUMERIC,
    pitch_std_hz     NUMERIC,
    energy_rms       NUMERIC,
    speaking_rate_wps NUMERIC,
    embedding        vector(384),   -- all-MiniLM-L6-v2
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS call_turns_call_id_idx ON docket.call_turns(call_id);
CREATE INDEX IF NOT EXISTS call_turns_cluster_id_idx ON docket.call_turns(cluster_id);

CREATE TABLE IF NOT EXISTS docket.versions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id        UUID NOT NULL REFERENCES docket.campaigns(id),
    version_number     INTEGER NOT NULL,
    prompt_text        TEXT NOT NULL,
    parent_version_id  UUID REFERENCES docket.versions(id),
    source             TEXT NOT NULL CHECK (source IN ('seed', 'gepa')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (campaign_id, version_number)
);
CREATE INDEX IF NOT EXISTS versions_campaign_id_idx ON docket.versions(campaign_id);

CREATE TABLE IF NOT EXISTS docket.scores (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id  UUID NOT NULL REFERENCES docket.versions(id),
    cluster_id  UUID NOT NULL REFERENCES docket.clusters(id),
    criterion   TEXT NOT NULL,
    score       NUMERIC NOT NULL,
    notes       TEXT,
    judged_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (version_id, cluster_id, criterion)
);
CREATE INDEX IF NOT EXISTS scores_version_id_idx ON docket.scores(version_id);
CREATE INDEX IF NOT EXISTS scores_cluster_id_idx ON docket.scores(cluster_id);
