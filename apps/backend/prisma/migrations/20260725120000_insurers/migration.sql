-- Aseguradoras reales (Insurer) + los 10 tipos de seguro reales del catálogo
-- LATAM (antes insurance_type solo tenía vida/auto/salud). Ver
-- docs/PLAN_CORRETAJE_ASEGURADORAS.md §3.4 — Colsubsidio/Tequendama
-- distribuyen, la aseguradora real es quien emite/responde.
-- Idempotente (IF NOT EXISTS / DO $$ ... $$) como el resto de migraciones.

-- 1) Enum insurance_type: agrega los 7 tipos que faltaban -------------------
-- Un bloque DO por valor (mismo patrón probado en 20260724100000_lead_scoring,
-- no se combinan varios ADD VALUE en un solo bloque).
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'hogar';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'viaje';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'pyme';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'accidentes';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'exequial';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'mascotas';
EXCEPTION WHEN duplicate_object THEN null;
END $$;
DO $$ BEGIN
    ALTER TYPE insurance_type ADD VALUE IF NOT EXISTS 'movilidad';
EXCEPTION WHEN duplicate_object THEN null;
END $$;

-- 2) Tabla insurers -----------------------------------------------------------
CREATE TABLE IF NOT EXISTS insurers (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre           TEXT NOT NULL,
    nit              TEXT,
    tipo_integracion TEXT,
    contact_email    TEXT,
    api_config       JSONB,
    activa           BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS insurers_nombre_key ON insurers(nombre);

-- 3) products.insurer_id -------------------------------------------------------
ALTER TABLE products ADD COLUMN IF NOT EXISTS insurer_id UUID;
ALTER TABLE products DROP CONSTRAINT IF EXISTS products_insurer_id_fkey;
ALTER TABLE products
    ADD CONSTRAINT products_insurer_id_fkey
    FOREIGN KEY (insurer_id) REFERENCES insurers(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_products_insurer ON products(insurer_id);

-- 4) policies.insurer_id (snapshot de la aseguradora al emitir) ---------------
ALTER TABLE policies ADD COLUMN IF NOT EXISTS insurer_id UUID;
ALTER TABLE policies DROP CONSTRAINT IF EXISTS policies_insurer_id_fkey;
ALTER TABLE policies
    ADD CONSTRAINT policies_insurer_id_fkey
    FOREIGN KEY (insurer_id) REFERENCES insurers(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_policies_insurer ON policies(insurer_id);

-- 5) Siembra de aseguradoras reales (mapa canónico LATAM ya usado en
--    data/market/catalogo_productos.json) — sin tipo_integracion todavía:
--    eso se define en §3.4/§5.2 del plan cuando el negocio confirme cómo se
--    entrega el expediente a cada una.
INSERT INTO insurers (nombre) VALUES
    ('Seguros Bolívar'), ('Sura'), ('Allianz'), ('MAPFRE'), ('Rimac'),
    ('AXA'), ('GNP Seguros'), ('Qualitas'), ('Palig'), ('ASSA'),
    ('Assist Card'), ('Seguros del Pacífico'),
    ('Seguros Colsubsidio'), ('Seguros Colsubsidio (aliado MetLife)')
ON CONFLICT (nombre) DO NOTHING;
