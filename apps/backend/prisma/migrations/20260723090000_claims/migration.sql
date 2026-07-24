-- Reclamos / siniestros (FNOL) del asistente — cierre del ciclo de la póliza.
-- Los reporta el chat/WhatsApp (claims_ai.py); el triage determinista (banderas
-- de fraude, resumen) queda registrado para el panel gerencial.
-- Idempotente (IF NOT EXISTS / DO $$ ... $$) como el resto de migraciones.

-- 1) Enum de estados del reclamo ---------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'claim_status') THEN
        CREATE TYPE claim_status AS ENUM
            ('reportado', 'en_revision', 'docs_pendientes',
             'aprobado', 'rechazado', 'pagado');
    END IF;
END
$$;

-- 2) Tabla claims -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claims (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID,
    policy_id           UUID,
    customer_id         UUID,
    claim_number        TEXT NOT NULL,
    insurance_type      insurance_type,
    status              claim_status NOT NULL DEFAULT 'reportado',
    description         TEXT,
    incident_date       DATE,
    amount_estimate_cop DECIMAL(14,2),
    fraud_score         DECIMAL(3,2),
    fraud_flags         JSONB DEFAULT '[]',
    documents           JSONB DEFAULT '[]',
    ai_summary          TEXT,
    created_at          TIMESTAMPTZ(6) NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);

-- 3) Unicidad, FKs e índices --------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS claims_claim_number_key ON claims(claim_number);

ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_team_id_fkey;
ALTER TABLE claims
    ADD CONSTRAINT claims_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_policy_id_fkey;
ALTER TABLE claims
    ADD CONSTRAINT claims_policy_id_fkey
    FOREIGN KEY (policy_id) REFERENCES policies(id) ON DELETE SET NULL;

ALTER TABLE claims DROP CONSTRAINT IF EXISTS claims_customer_id_fkey;
ALTER TABLE claims
    ADD CONSTRAINT claims_customer_id_fkey
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_claims_team ON claims(team_id);
CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id);

-- 4) Seed demo (idempotente por IDs fijos): una póliza que vence en 15 días y
--    un reclamo en revisión con banderas de fraude, para que la demo muestre
--    de inmediato la renovación proactiva, el ClaimsPanel y proponer_renovacion.
INSERT INTO customers (id, team_id, full_name, email, phone, document_type,
                       document_id, city, consent_data, consent_at)
VALUES ('22222222-2222-4222-8222-222222222201',
        '11111111-1111-1111-1111-111111111111',
        'Carolina Rojas (demo)', 'carolina.demo@mail.com', '+573005550101',
        'CC', '900000001', 'Bogotá', TRUE, now())
ON CONFLICT (id) DO NOTHING;

INSERT INTO leads (id, team_id, customer_id, insurance_type, status, intent,
                   first_contact_at, closed_at)
SELECT '22222222-2222-4222-8222-222222222202',
       '11111111-1111-1111-1111-111111111111',
       '22222222-2222-4222-8222-222222222201',
       'auto', 'cerrado_ganado', 'caliente', now(), now()
WHERE NOT EXISTS (SELECT 1 FROM leads
                  WHERE id = '22222222-2222-4222-8222-222222222202');

INSERT INTO quotes (id, team_id, lead_id, product_id, coverage,
                    monthly_premium_cop, status)
SELECT '22222222-2222-4222-8222-222222222203',
       '11111111-1111-1111-1111-111111111111',
       '22222222-2222-4222-8222-222222222202',
       p.id, '{"resumen": "Auto Total (demo)"}'::jsonb, 185000, 'aceptada'
FROM products p
WHERE p.insurance_type = 'auto' AND p.is_active
  AND NOT EXISTS (SELECT 1 FROM quotes
                  WHERE id = '22222222-2222-4222-8222-222222222203')
LIMIT 1;

-- Vence en 15 días → dispara el nudge renovacion_proxima y la alerta gerencial.
INSERT INTO policies (id, team_id, quote_id, customer_id, policy_number,
                      status, start_date, end_date, monthly_premium_cop)
SELECT '22222222-2222-4222-8222-222222222204',
       '11111111-1111-1111-1111-111111111111',
       '22222222-2222-4222-8222-222222222203',
       '22222222-2222-4222-8222-222222222201',
       'POL-2026-DEMO01', 'vigente',
       CURRENT_DATE - INTERVAL '350 days', CURRENT_DATE + INTERVAL '15 days',
       185000
WHERE EXISTS (SELECT 1 FROM quotes
              WHERE id = '22222222-2222-4222-8222-222222222203')
  AND NOT EXISTS (SELECT 1 FROM policies
                  WHERE policy_number = 'POL-2026-DEMO01');

INSERT INTO claims (id, team_id, policy_id, customer_id, claim_number,
                    insurance_type, status, description, incident_date,
                    amount_estimate_cop, fraud_score, fraud_flags, ai_summary)
SELECT '22222222-2222-4222-8222-222222222205',
       '11111111-1111-1111-1111-111111111111',
       p.id, '22222222-2222-4222-8222-222222222201',
       'CLM-2026-DEMO01', 'auto', 'en_revision',
       'Colisión leve en la Av. Boyacá; daño en la puerta trasera derecha.',
       CURRENT_DATE - INTERVAL '3 days', 2400000, 0.20,
       '["reclamos_previos: el cliente ya tiene 1 reclamo(s)"]'::jsonb,
       'Auto: colisión leve · Estimado 2.400.000 COP'
FROM policies p
WHERE p.policy_number = 'POL-2026-DEMO01'
  AND NOT EXISTS (SELECT 1 FROM claims WHERE claim_number = 'CLM-2026-DEMO01');
