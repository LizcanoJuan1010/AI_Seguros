CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE user_role AS ENUM ('agente', 'gerente', 'admin');
CREATE TYPE user_status AS ENUM ('activo', 'inactivo', 'vacaciones');
CREATE TYPE insurance_type AS ENUM ('vida', 'auto', 'salud');
CREATE TYPE call_status AS ENUM ('en_curso', 'completada', 'abandonada', 'transferida_humano', 'fallida');
CREATE TYPE lead_intent AS ENUM ('caliente', 'tibio', 'frio');
CREATE TYPE lead_status AS ENUM ('nuevo', 'contactado', 'cotizado', 'negociacion', 'cerrado_ganado', 'cerrado_perdido');
CREATE TYPE quote_status AS ENUM ('borrador', 'enviada', 'aceptada', 'rechazada', 'vencida');
CREATE TYPE policy_status AS ENUM ('vigente', 'cancelada', 'vencida', 'suspendida');
CREATE TYPE speaker_type AS ENUM ('ia', 'cliente');
CREATE TYPE event_type AS ENUM ('llamada_saliente', 'whatsapp', 'email', 'reunion', 'nota', 'cambio_estado', 'reasignacion');

CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    manager_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    role user_role NOT NULL DEFAULT 'agente',
    status user_status NOT NULL DEFAULT 'activo',
    avatar_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE teams
    ADD CONSTRAINT fk_teams_manager
    FOREIGN KEY (manager_id) REFERENCES users(id) ON DELETE SET NULL;

CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name TEXT,
    email TEXT,
    phone TEXT,
    document_type TEXT DEFAULT 'CC',
    document_id TEXT,
    birth_date DATE,
    city TEXT,
    department TEXT,
    consent_data BOOLEAN NOT NULL DEFAULT false,
    consent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_type, document_id)
);
CREATE INDEX idx_customers_phone ON customers(phone);

CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    insurance_type insurance_type NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    base_premium_cop NUMERIC(14,2),
    coverage_schema JSONB,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE ai_calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) ON DELETE SET NULL,
    status call_status NOT NULL DEFAULT 'en_curso',
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    duration_sec INT GENERATED ALWAYS AS
        (EXTRACT(EPOCH FROM (ended_at - started_at))::INT) STORED,
    recording_url TEXT,
    summary TEXT,
    intent lead_intent,
    intent_score NUMERIC(3,2) CHECK (intent_score BETWEEN 0 AND 1),
    sentiment TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ai_calls_customer ON ai_calls(customer_id);
CREATE INDEX idx_ai_calls_started_at ON ai_calls(started_at DESC);

CREATE TABLE call_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL REFERENCES ai_calls(id) ON DELETE CASCADE,
    speaker speaker_type NOT NULL,
    content TEXT NOT NULL,
    spoken_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_call_messages_call ON call_messages(call_id, spoken_at);

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    ai_call_id UUID UNIQUE REFERENCES ai_calls(id) ON DELETE SET NULL,
    agent_id UUID REFERENCES users(id) ON DELETE SET NULL,
    insurance_type insurance_type,
    status lead_status NOT NULL DEFAULT 'nuevo',
    intent lead_intent NOT NULL DEFAULT 'tibio',
    assigned_at TIMESTAMPTZ,
    first_contact_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    lost_reason TEXT,
    ai_next_steps JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_leads_agent_status ON leads(agent_id, status);
CREATE INDEX idx_leads_intent ON leads(intent) WHERE status IN ('nuevo', 'contactado');
CREATE INDEX idx_leads_created_at ON leads(created_at DESC);

CREATE TABLE lead_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES users(id) ON DELETE SET NULL,
    event_type event_type NOT NULL,
    notes TEXT,
    payload JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_lead_events_lead ON lead_events(lead_id, created_at);

CREATE TABLE quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id),
    created_by UUID REFERENCES users(id),
    coverage JSONB NOT NULL DEFAULT '{}',
    monthly_premium_cop NUMERIC(14,2) NOT NULL,
    status quote_status NOT NULL DEFAULT 'borrador',
    valid_until DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_quotes_lead ON quotes(lead_id);

CREATE TABLE policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quote_id UUID NOT NULL UNIQUE REFERENCES quotes(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    agent_id UUID REFERENCES users(id),
    policy_number TEXT NOT NULL UNIQUE,
    status policy_status NOT NULL DEFAULT 'vigente',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    monthly_premium_cop NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (end_date > start_date)
);
CREATE INDEX idx_policies_agent ON policies(agent_id);

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES users(id) ON DELETE SET NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'media',
    resolved BOOLEAN NOT NULL DEFAULT false,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alerts_team_open ON alerts(team_id) WHERE resolved = false;

CREATE VIEW v_agent_performance AS
SELECT
    u.id AS agent_id,
    u.full_name,
    u.team_id,
    COUNT(DISTINCT l.id) AS leads_recibidos,
    COUNT(DISTINCT le.id) FILTER
        (WHERE le.event_type = 'llamada_saliente') AS llamadas_realizadas,
    COUNT(DISTINCT p.id) AS polizas_cerradas,
    ROUND(
        COUNT(DISTINCT p.id)::NUMERIC
        / NULLIF(COUNT(DISTINCT l.id), 0) * 100, 1) AS conversion_pct,
    COALESCE(SUM(p.monthly_premium_cop), 0) AS revenue_mensual_cop
FROM users u
LEFT JOIN leads l ON l.agent_id = u.id
LEFT JOIN lead_events le ON le.agent_id = u.id
LEFT JOIN policies p ON p.agent_id = u.id
WHERE u.role = 'agente'
GROUP BY u.id, u.full_name, u.team_id;

CREATE VIEW v_daily_kpis AS
SELECT
    COUNT(*) FILTER (WHERE ac.started_at::DATE = CURRENT_DATE) AS llamadas_ia_hoy,
    ROUND(AVG(ac.duration_sec) FILTER
        (WHERE ac.status = 'completada'), 0) AS duracion_promedio_sec,
    (SELECT COUNT(*) FROM policies
        WHERE created_at::DATE = CURRENT_DATE) AS polizas_hoy,
    (SELECT COALESCE(SUM(monthly_premium_cop), 0) FROM policies
        WHERE created_at::DATE = CURRENT_DATE) AS revenue_hoy_cop
FROM ai_calls ac;

CREATE VIEW v_hot_leads_uncontacted AS
SELECT l.id, l.agent_id, u.full_name AS agent_name, l.created_at,
       now() - l.created_at AS tiempo_sin_contacto
FROM leads l
LEFT JOIN users u ON u.id = l.agent_id
WHERE l.intent = 'caliente'
  AND l.status = 'nuevo'
  AND l.first_contact_at IS NULL
  AND l.created_at < now() - INTERVAL '2 hours';

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_customers_updated BEFORE UPDATE ON customers
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_leads_updated BEFORE UPDATE ON leads
FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_quotes_updated BEFORE UPDATE ON quotes
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

INSERT INTO products (insurance_type, name, base_premium_cop, coverage_schema) VALUES
('vida', 'Vida Esencial', 45000, '{"muerte": true, "invalidez": true, "beneficiarios": []}'),
('auto', 'Auto Total', 120000, '{"todo_riesgo": true, "rc": 640000000, "asistencia": true}'),
('salud', 'Salud Integral', 95000, '{"hospitalizacion": true, "consultas": true, "red": "nacional"}');
