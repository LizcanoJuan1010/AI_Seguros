-- Pagos reales (Polar sandbox) del cierre autónomo del asistente.
-- La tabla es el sistema de registro de cada cobro: la crea el servicio IA al
-- generar el checkout y la actualizan los webhooks de Polar y verificar_pago.
-- Idempotente (IF NOT EXISTS / DO $$ ... $$) como el resto de migraciones.

-- 1) Enum de estados canónicos (+ refund_requested para aclaraciones) --------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'payment_status') THEN
        CREATE TYPE payment_status AS ENUM
            ('pending', 'approved', 'declined', 'voided', 'error', 'refund_requested');
    END IF;
END
$$;

-- 2) Tabla payments ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id        UUID,
    reference      TEXT NOT NULL,
    provider       TEXT NOT NULL DEFAULT 'polar',
    link_id        TEXT,
    transaction_id TEXT,
    checkout_url   TEXT,
    amount_cop     DECIMAL(14,2) NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'COP',
    method         TEXT,
    status         payment_status NOT NULL DEFAULT 'pending',
    concept        TEXT,
    session_key    TEXT,
    dispute_reason TEXT,
    metadata       JSONB DEFAULT '{}',
    created_at     TIMESTAMPTZ(6) NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);

-- 3) Unicidad, FK e índices --------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS payments_reference_key ON payments(reference);

ALTER TABLE payments DROP CONSTRAINT IF EXISTS payments_team_id_fkey;
ALTER TABLE payments
    ADD CONSTRAINT payments_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_payments_team ON payments(team_id);
CREATE INDEX IF NOT EXISTS idx_payments_link ON payments(link_id);
