-- Clientes: notas de texto libre + documentos adjuntos.
-- Habilita crear/editar clientes desde la UI del gerente y adjuntarles archivos
-- (cédula, RUT, PDFs). El binario vive en disco (CUSTOMER_UPLOADS_DIR); esta
-- tabla guarda solo la metadata. Idempotente (IF NOT EXISTS) como el resto.

-- 1) Campo de notas en customers ---------------------------------------------
ALTER TABLE customers ADD COLUMN IF NOT EXISTS notes TEXT;

-- 2) Tabla de documentos del cliente -----------------------------------------
CREATE TABLE IF NOT EXISTS customer_documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL,
    team_id     UUID,
    filename    TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    mime_type   TEXT NOT NULL,
    size_bytes  INTEGER NOT NULL,
    kind        TEXT,
    created_at  TIMESTAMPTZ(6) NOT NULL DEFAULT now()
);

-- 3) FK e índice --------------------------------------------------------------
ALTER TABLE customer_documents DROP CONSTRAINT IF EXISTS customer_documents_customer_id_fkey;
ALTER TABLE customer_documents
    ADD CONSTRAINT customer_documents_customer_id_fkey
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_customer_documents_customer ON customer_documents(customer_id);
