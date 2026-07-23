--
-- PostgreSQL database dump
--

\restrict b3mo1FwChUSeaT8DIUJOAepLcUtycXg42ISRyFvGUC8amea4DsSi9YcSpTFCwxA

-- Dumped from database version 16.14
-- Dumped by pg_dump version 16.14

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: seguria; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA seguria;


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: call_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.call_status AS ENUM (
    'en_curso',
    'completada',
    'abandonada',
    'transferida_humano',
    'fallida'
);


--
-- Name: event_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.event_type AS ENUM (
    'llamada_saliente',
    'whatsapp',
    'email',
    'reunion',
    'nota',
    'cambio_estado',
    'reasignacion'
);


--
-- Name: insurance_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.insurance_type AS ENUM (
    'vida',
    'auto',
    'salud'
);


--
-- Name: lead_intent; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.lead_intent AS ENUM (
    'caliente',
    'tibio',
    'frio'
);


--
-- Name: lead_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.lead_status AS ENUM (
    'nuevo',
    'contactado',
    'cotizado',
    'negociacion',
    'cerrado_ganado',
    'cerrado_perdido'
);


--
-- Name: policy_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.policy_status AS ENUM (
    'vigente',
    'cancelada',
    'vencida',
    'suspendida'
);


--
-- Name: quote_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.quote_status AS ENUM (
    'borrador',
    'enviada',
    'aceptada',
    'rechazada',
    'vencida'
);


--
-- Name: speaker_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.speaker_type AS ENUM (
    'ia',
    'cliente'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'agente',
    'gerente',
    'admin'
);


--
-- Name: user_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_status AS ENUM (
    'activo',
    'inactivo',
    'vacaciones'
);


--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: _prisma_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public._prisma_migrations (
    id character varying(36) NOT NULL,
    checksum character varying(64) NOT NULL,
    finished_at timestamp with time zone,
    migration_name character varying(255) NOT NULL,
    logs text,
    rolled_back_at timestamp with time zone,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    applied_steps_count integer DEFAULT 0 NOT NULL
);


--
-- Name: ai_calls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ai_calls (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    customer_id uuid,
    status public.call_status DEFAULT 'en_curso'::public.call_status NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    ended_at timestamp with time zone,
    duration_sec integer GENERATED ALWAYS AS ((EXTRACT(epoch FROM (ended_at - started_at)))::integer) STORED,
    recording_url text,
    summary text,
    intent public.lead_intent,
    intent_score numeric(3,2),
    sentiment text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ai_calls_intent_score_check CHECK (((intent_score >= (0)::numeric) AND (intent_score <= (1)::numeric)))
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    team_id uuid,
    lead_id uuid,
    agent_id uuid,
    message text NOT NULL,
    severity text DEFAULT 'media'::text NOT NULL,
    resolved boolean DEFAULT false NOT NULL,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: call_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_messages (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    call_id uuid NOT NULL,
    speaker public.speaker_type NOT NULL,
    content text NOT NULL,
    spoken_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: customers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.customers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    full_name text,
    email text,
    phone text,
    document_type text DEFAULT 'CC'::text,
    document_id text,
    birth_date date,
    city text,
    department text,
    consent_data boolean DEFAULT false NOT NULL,
    consent_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    team_id uuid
);


--
-- Name: lead_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lead_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    lead_id uuid NOT NULL,
    agent_id uuid,
    event_type public.event_type NOT NULL,
    notes text,
    payload jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    customer_id uuid NOT NULL,
    ai_call_id uuid,
    agent_id uuid,
    insurance_type public.insurance_type,
    status public.lead_status DEFAULT 'nuevo'::public.lead_status NOT NULL,
    intent public.lead_intent DEFAULT 'tibio'::public.lead_intent NOT NULL,
    assigned_at timestamp with time zone,
    first_contact_at timestamp with time zone,
    closed_at timestamp with time zone,
    lost_reason text,
    ai_next_steps jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    team_id uuid
);


--
-- Name: policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policies (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    quote_id uuid NOT NULL,
    customer_id uuid NOT NULL,
    agent_id uuid,
    policy_number text NOT NULL,
    status public.policy_status DEFAULT 'vigente'::public.policy_status NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    monthly_premium_cop numeric(14,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    team_id uuid,
    CONSTRAINT policies_check CHECK ((end_date > start_date))
);


--
-- Name: products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.products (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    insurance_type public.insurance_type NOT NULL,
    name text NOT NULL,
    description text,
    base_premium_cop numeric(14,2),
    coverage_schema jsonb,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: quotes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.quotes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    lead_id uuid NOT NULL,
    product_id uuid NOT NULL,
    created_by uuid,
    coverage jsonb DEFAULT '{}'::jsonb NOT NULL,
    monthly_premium_cop numeric(14,2) NOT NULL,
    status public.quote_status DEFAULT 'borrador'::public.quote_status NOT NULL,
    valid_until date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    team_id uuid
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    manager_id uuid,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    team_id uuid,
    full_name text NOT NULL,
    email text NOT NULL,
    phone text,
    role public.user_role DEFAULT 'agente'::public.user_role NOT NULL,
    status public.user_status DEFAULT 'activo'::public.user_status NOT NULL,
    avatar_url text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    password_hash text
);


--
-- Name: v_agent_performance; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_agent_performance AS
 SELECT u.id AS agent_id,
    u.full_name,
    u.team_id,
    count(DISTINCT l.id) AS leads_recibidos,
    count(DISTINCT le.id) FILTER (WHERE (le.event_type = 'llamada_saliente'::public.event_type)) AS llamadas_realizadas,
    count(DISTINCT p.id) AS polizas_cerradas,
    round((((count(DISTINCT p.id))::numeric / (NULLIF(count(DISTINCT l.id), 0))::numeric) * (100)::numeric), 1) AS conversion_pct,
    COALESCE(sum(p.monthly_premium_cop), (0)::numeric) AS revenue_mensual_cop
   FROM (((public.users u
     LEFT JOIN public.leads l ON ((l.agent_id = u.id)))
     LEFT JOIN public.lead_events le ON ((le.agent_id = u.id)))
     LEFT JOIN public.policies p ON ((p.agent_id = u.id)))
  WHERE (u.role = 'agente'::public.user_role)
  GROUP BY u.id, u.full_name, u.team_id;


--
-- Name: v_daily_kpis; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_daily_kpis AS
 SELECT count(*) FILTER (WHERE ((started_at)::date = CURRENT_DATE)) AS llamadas_ia_hoy,
    round(avg(duration_sec) FILTER (WHERE (status = 'completada'::public.call_status)), 0) AS duracion_promedio_sec,
    ( SELECT count(*) AS count
           FROM public.policies
          WHERE ((policies.created_at)::date = CURRENT_DATE)) AS polizas_hoy,
    ( SELECT COALESCE(sum(policies.monthly_premium_cop), (0)::numeric) AS "coalesce"
           FROM public.policies
          WHERE ((policies.created_at)::date = CURRENT_DATE)) AS revenue_hoy_cop
   FROM public.ai_calls ac;


--
-- Name: v_hot_leads_uncontacted; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_hot_leads_uncontacted AS
 SELECT l.id,
    l.team_id,
    l.agent_id,
    u.full_name AS agent_name,
    l.created_at,
    (now() - l.created_at) AS tiempo_sin_contacto
   FROM (public.leads l
     LEFT JOIN public.users u ON ((u.id = l.agent_id)))
  WHERE ((l.intent = 'caliente'::public.lead_intent) AND (l.status = 'nuevo'::public.lead_status) AND (l.first_contact_at IS NULL) AND (l.created_at < (now() - '02:00:00'::interval)));


--
-- Name: chat_history; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.chat_history (
    session_id text NOT NULL,
    seq integer NOT NULL,
    message text
);


--
-- Name: checkout_session; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.checkout_session (
    session_key text NOT NULL,
    full_name text,
    document_type text DEFAULT 'CC'::text,
    document_id text,
    birth_date text,
    email text,
    phone text,
    city text,
    department text,
    consent integer DEFAULT 0,
    consent_at text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: conversations; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.conversations (
    id bigint NOT NULL,
    phone text,
    role text,
    channel text DEFAULT 'whatsapp'::text,
    message text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: seguria; Owner: -
--

ALTER TABLE seguria.conversations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME seguria.conversations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: fx_rates; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.fx_rates (
    currency text NOT NULL,
    date text NOT NULL,
    usd_rate double precision NOT NULL
);


--
-- Name: intake_session; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.intake_session (
    session_key text NOT NULL,
    datos text DEFAULT '{}'::text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: leads; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.leads (
    id bigint NOT NULL,
    phone text,
    name text,
    country text,
    age integer,
    stage text DEFAULT 'nuevo'::text,
    source text DEFAULT 'whatsapp'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: leads_id_seq; Type: SEQUENCE; Schema: seguria; Owner: -
--

ALTER TABLE seguria.leads ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME seguria.leads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: memory; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.memory (
    id bigint NOT NULL,
    tenant_id text DEFAULT 'demo'::text NOT NULL,
    user_id text NOT NULL,
    content text NOT NULL,
    category text DEFAULT 'general'::text NOT NULL,
    hash text NOT NULL,
    score integer DEFAULT 1 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: memory_id_seq; Type: SEQUENCE; Schema: seguria; Owner: -
--

CREATE SEQUENCE seguria.memory_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: memory_id_seq; Type: SEQUENCE OWNED BY; Schema: seguria; Owner: -
--

ALTER SEQUENCE seguria.memory_id_seq OWNED BY seguria.memory.id;


--
-- Name: products; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.products (
    id text NOT NULL,
    tipo text NOT NULL,
    nombre text NOT NULL,
    aseguradora text NOT NULL,
    paises text NOT NULL,
    suma_base_usd double precision NOT NULL,
    prima_base_usd double precision NOT NULL,
    prima_por_dia integer DEFAULT 0,
    coberturas text NOT NULL,
    factores text NOT NULL
);


--
-- Name: quotes; Type: TABLE; Schema: seguria; Owner: -
--

CREATE TABLE seguria.quotes (
    id bigint NOT NULL,
    lead_id bigint,
    product_id text,
    country text NOT NULL,
    currency text NOT NULL,
    sum_assured_usd double precision NOT NULL,
    premium_monthly_usd double precision NOT NULL,
    premium_monthly_local double precision NOT NULL,
    breakdown text NOT NULL,
    status text DEFAULT 'emitida'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: quotes_id_seq; Type: SEQUENCE; Schema: seguria; Owner: -
--

ALTER TABLE seguria.quotes ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME seguria.quotes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: memory id; Type: DEFAULT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.memory ALTER COLUMN id SET DEFAULT nextval('seguria.memory_id_seq'::regclass);


--
-- Name: _prisma_migrations _prisma_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public._prisma_migrations
    ADD CONSTRAINT _prisma_migrations_pkey PRIMARY KEY (id);


--
-- Name: ai_calls ai_calls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_calls
    ADD CONSTRAINT ai_calls_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: call_messages call_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_messages
    ADD CONSTRAINT call_messages_pkey PRIMARY KEY (id);


--
-- Name: customers customers_document_type_document_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_document_type_document_id_key UNIQUE (document_type, document_id);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: lead_events lead_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_events
    ADD CONSTRAINT lead_events_pkey PRIMARY KEY (id);


--
-- Name: leads leads_ai_call_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_ai_call_id_key UNIQUE (ai_call_id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (id);


--
-- Name: policies policies_policy_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_policy_number_key UNIQUE (policy_number);


--
-- Name: policies policies_quote_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_quote_id_key UNIQUE (quote_id);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: quotes quotes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_pkey PRIMARY KEY (id);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: chat_history chat_history_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.chat_history
    ADD CONSTRAINT chat_history_pkey PRIMARY KEY (session_id, seq);


--
-- Name: checkout_session checkout_session_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.checkout_session
    ADD CONSTRAINT checkout_session_pkey PRIMARY KEY (session_key);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: fx_rates fx_rates_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.fx_rates
    ADD CONSTRAINT fx_rates_pkey PRIMARY KEY (currency, date);


--
-- Name: intake_session intake_session_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.intake_session
    ADD CONSTRAINT intake_session_pkey PRIMARY KEY (session_key);


--
-- Name: leads leads_phone_key; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.leads
    ADD CONSTRAINT leads_phone_key UNIQUE (phone);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: memory memory_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.memory
    ADD CONSTRAINT memory_pkey PRIMARY KEY (id);


--
-- Name: memory memory_tenant_user_hash_key; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.memory
    ADD CONSTRAINT memory_tenant_user_hash_key UNIQUE (tenant_id, user_id, hash);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: quotes quotes_pkey; Type: CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.quotes
    ADD CONSTRAINT quotes_pkey PRIMARY KEY (id);


--
-- Name: idx_ai_calls_customer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_calls_customer ON public.ai_calls USING btree (customer_id);


--
-- Name: idx_ai_calls_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ai_calls_started_at ON public.ai_calls USING btree (started_at DESC);


--
-- Name: idx_alerts_team_open; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alerts_team_open ON public.alerts USING btree (team_id) WHERE (resolved = false);


--
-- Name: idx_call_messages_call; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_call_messages_call ON public.call_messages USING btree (call_id, spoken_at);


--
-- Name: idx_customers_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_customers_phone ON public.customers USING btree (phone);


--
-- Name: idx_customers_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_customers_team ON public.customers USING btree (team_id);


--
-- Name: idx_lead_events_lead; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lead_events_lead ON public.lead_events USING btree (lead_id, created_at);


--
-- Name: idx_leads_agent_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_agent_status ON public.leads USING btree (agent_id, status);


--
-- Name: idx_leads_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_created_at ON public.leads USING btree (created_at DESC);


--
-- Name: idx_leads_intent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_intent ON public.leads USING btree (intent) WHERE (status = ANY (ARRAY['nuevo'::public.lead_status, 'contactado'::public.lead_status]));


--
-- Name: idx_leads_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_team ON public.leads USING btree (team_id);


--
-- Name: idx_policies_agent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_policies_agent ON public.policies USING btree (agent_id);


--
-- Name: idx_policies_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_policies_team ON public.policies USING btree (team_id);


--
-- Name: idx_quotes_lead; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quotes_lead ON public.quotes USING btree (lead_id);


--
-- Name: idx_quotes_team; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_quotes_team ON public.quotes USING btree (team_id);


--
-- Name: memory_tenant_user_rank; Type: INDEX; Schema: seguria; Owner: -
--

CREATE INDEX memory_tenant_user_rank ON seguria.memory USING btree (tenant_id, user_id, score DESC, updated_at DESC);


--
-- Name: customers trg_customers_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_customers_updated BEFORE UPDATE ON public.customers FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: leads trg_leads_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_leads_updated BEFORE UPDATE ON public.leads FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: quotes trg_quotes_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_quotes_updated BEFORE UPDATE ON public.quotes FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: users trg_users_updated; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


--
-- Name: ai_calls ai_calls_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ai_calls
    ADD CONSTRAINT ai_calls_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: alerts alerts_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE CASCADE;


--
-- Name: call_messages call_messages_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_messages
    ADD CONSTRAINT call_messages_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.ai_calls(id) ON DELETE CASCADE;


--
-- Name: customers customers_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.customers
    ADD CONSTRAINT customers_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: teams fk_teams_manager; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT fk_teams_manager FOREIGN KEY (manager_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: lead_events lead_events_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_events
    ADD CONSTRAINT lead_events_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: lead_events lead_events_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_events
    ADD CONSTRAINT lead_events_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;


--
-- Name: leads leads_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: leads leads_ai_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_ai_call_id_fkey FOREIGN KEY (ai_call_id) REFERENCES public.ai_calls(id) ON DELETE SET NULL;


--
-- Name: leads leads_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id) ON DELETE CASCADE;


--
-- Name: leads leads_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: policies policies_agent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_agent_id_fkey FOREIGN KEY (agent_id) REFERENCES public.users(id);


--
-- Name: policies policies_customer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES public.customers(id);


--
-- Name: policies policies_quote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_quote_id_fkey FOREIGN KEY (quote_id) REFERENCES public.quotes(id);


--
-- Name: policies policies_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: quotes quotes_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: quotes quotes_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;


--
-- Name: quotes quotes_product_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_product_id_fkey FOREIGN KEY (product_id) REFERENCES public.products(id);


--
-- Name: quotes quotes_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.quotes
    ADD CONSTRAINT quotes_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: users users_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id) ON DELETE SET NULL;


--
-- Name: quotes quotes_lead_id_fkey; Type: FK CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.quotes
    ADD CONSTRAINT quotes_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES seguria.leads(id);


--
-- Name: quotes quotes_product_id_fkey; Type: FK CONSTRAINT; Schema: seguria; Owner: -
--

ALTER TABLE ONLY seguria.quotes
    ADD CONSTRAINT quotes_product_id_fkey FOREIGN KEY (product_id) REFERENCES seguria.products(id);


--
-- PostgreSQL database dump complete
--

\unrestrict b3mo1FwChUSeaT8DIUJOAepLcUtycXg42ISRyFvGUC8amea4DsSi9YcSpTFCwxA

