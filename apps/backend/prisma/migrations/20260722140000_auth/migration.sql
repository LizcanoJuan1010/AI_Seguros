-- Auth: contraseña (hash bcrypt) en users + usuarios demo por tenant.
-- El tenant (Team) sale del login: cada usuario demo pertenece a su team.
-- Script idempotente: ADD COLUMN IF NOT EXISTS + INSERT ... ON CONFLICT DO UPDATE.

-- 1) Columna password_hash -------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- 2) Usuarios demo (contraseña "demo123", bcrypt cost 10) ------------------
--    team A = 1111-...-1111 (Colsubsidio Demo), team B = 2222-...-2222.
--    Los teams se siembran en la migración multitenant previa.
INSERT INTO users (id, team_id, full_name, email, role, password_hash) VALUES
  (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 'Gerente Colsubsidio', 'gerente@colsubsidio.demo', 'gerente', '$2b$10$0jUcFyvL75DElZTMooHioOV1dQ6oKXL5/K4rAXCycduWs70UQQI9K'),
  (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 'Agente Colsubsidio',  'agente@colsubsidio.demo',  'agente',  '$2b$10$0jUcFyvL75DElZTMooHioOV1dQ6oKXL5/K4rAXCycduWs70UQQI9K'),
  (gen_random_uuid(), '22222222-2222-2222-2222-222222222222', 'Gerente Tenant B',    'gerente@tenantb.demo',     'gerente', '$2b$10$0jUcFyvL75DElZTMooHioOV1dQ6oKXL5/K4rAXCycduWs70UQQI9K')
ON CONFLICT (email) DO UPDATE SET
  password_hash = EXCLUDED.password_hash,
  team_id       = EXCLUDED.team_id,
  role          = EXCLUDED.role;
