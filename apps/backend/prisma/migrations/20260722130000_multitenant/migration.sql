-- Multitenancy: aislamiento por organización (Team) en el dominio de venta.
-- Añade team_id (tenant) a customers, leads, quotes y policies, con FK opcional a teams.
-- Se deja nullable + ON DELETE SET NULL para no romper filas existentes ni la cadena.
-- El script es idempotente (IF EXISTS / IF NOT EXISTS / ON CONFLICT).

-- 1) Columnas team_id ------------------------------------------------------
ALTER TABLE customers ADD COLUMN IF NOT EXISTS team_id UUID;
ALTER TABLE leads     ADD COLUMN IF NOT EXISTS team_id UUID;
ALTER TABLE quotes    ADD COLUMN IF NOT EXISTS team_id UUID;
ALTER TABLE policies  ADD COLUMN IF NOT EXISTS team_id UUID;

-- 2) Foreign keys a teams(id) ---------------------------------------------
ALTER TABLE customers DROP CONSTRAINT IF EXISTS customers_team_id_fkey;
ALTER TABLE customers
    ADD CONSTRAINT customers_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

ALTER TABLE leads DROP CONSTRAINT IF EXISTS leads_team_id_fkey;
ALTER TABLE leads
    ADD CONSTRAINT leads_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

ALTER TABLE quotes DROP CONSTRAINT IF EXISTS quotes_team_id_fkey;
ALTER TABLE quotes
    ADD CONSTRAINT quotes_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

ALTER TABLE policies DROP CONSTRAINT IF EXISTS policies_team_id_fkey;
ALTER TABLE policies
    ADD CONSTRAINT policies_team_id_fkey
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL;

-- 3) Índices por tenant ----------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_customers_team ON customers(team_id);
CREATE INDEX IF NOT EXISTS idx_leads_team     ON leads(team_id);
CREATE INDEX IF NOT EXISTS idx_quotes_team    ON quotes(team_id);
CREATE INDEX IF NOT EXISTS idx_policies_team  ON policies(team_id);

-- 4) Teams sembrados (tenant demo + tenant B para pruebas de aislamiento) --
INSERT INTO teams (id, name) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Colsubsidio Demo'),
    ('22222222-2222-2222-2222-222222222222', 'Tenant B Demo')
ON CONFLICT (id) DO NOTHING;

-- 5) Vista de leads calientes con team_id para permitir scoping por tenant --
-- DROP + CREATE (no REPLACE) porque cambia el orden/lista de columnas.
DROP VIEW IF EXISTS v_hot_leads_uncontacted;
CREATE VIEW v_hot_leads_uncontacted AS
SELECT l.id, l.team_id, l.agent_id, u.full_name AS agent_name, l.created_at,
       now() - l.created_at AS tiempo_sin_contacto
FROM leads l
LEFT JOIN users u ON u.id = l.agent_id
WHERE l.intent = 'caliente'
  AND l.status = 'nuevo'
  AND l.first_contact_at IS NULL
  AND l.created_at < now() - INTERVAL '2 hours';
