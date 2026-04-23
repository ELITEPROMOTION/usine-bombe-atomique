-- ============================================================
-- 006_tenants_rls.sql - Multi-tenancy (12 entites Groupe Dendani)
--                       + Row-Level Security + tenant_id sur tables
-- ============================================================

-- 1. Table tenants
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code VARCHAR(40) NOT NULL UNIQUE,
    label VARCHAR(200) NOT NULL,
    parent_code VARCHAR(40),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Tenant par defaut (pour retrocompat des lignes existantes)
INSERT INTO tenants (id, code, label) VALUES
  ('00000000-0000-0000-0000-000000000000', 'default', 'Defaut (retrocompatibilite)')
ON CONFLICT (code) DO NOTHING;

-- 3. 12 entites metier du Groupe Dendani
INSERT INTO tenants (code, label, parent_code) VALUES
  ('groupe-dendani',     'Groupe Dendani (holding)',         NULL),
  ('irene',              'Residence IRENE - Alger',          'groupe-dendani'),
  ('aurea',              'Residence AUREA - Oran',           'groupe-dendani'),
  ('magnolia',           'Residence MAGNOLIA - Constantine', 'groupe-dendani'),
  ('asteria',            'Residence ASTERIA - Annaba',       'groupe-dendani'),
  ('dendani-promotion',  'Dendani Promotion Immobiliere',    'groupe-dendani'),
  ('dendani-construction','Dendani Construction',            'groupe-dendani'),
  ('dendani-finance',    'Dendani Finance',                  'groupe-dendani'),
  ('dendani-tech',       'Dendani Tech (UBA)',               'groupe-dendani'),
  ('dendani-hr',         'Dendani RH/Paie',                  'groupe-dendani'),
  ('dendani-legal',      'Dendani Legal',                    'groupe-dendani'),
  ('dendani-compta',     'Dendani Comptabilite SCF',         'groupe-dendani')
ON CONFLICT (code) DO NOTHING;

-- 4. Ajouter tenant_id sur tables metier
ALTER TABLE tasks           ADD COLUMN IF NOT EXISTS tenant_id UUID
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES tenants(id);
ALTER TABLE sessions        ADD COLUMN IF NOT EXISTS tenant_id UUID
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES tenants(id);
ALTER TABLE artifacts       ADD COLUMN IF NOT EXISTS tenant_id UUID
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES tenants(id);
ALTER TABLE project_memory  ADD COLUMN IF NOT EXISTS tenant_id UUID
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES tenants(id);

CREATE INDEX IF NOT EXISTS idx_tasks_tenant          ON tasks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_tenant      ON artifacts(tenant_id);
CREATE INDEX IF NOT EXISTS idx_project_memory_tenant ON project_memory(tenant_id);

-- 5. Ajouter tenant + super_admin sur users
ALTER TABLE users ADD COLUMN IF NOT EXISTS tenant_id UUID
  NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000' REFERENCES tenants(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_super_admin BOOLEAN NOT NULL DEFAULT FALSE;

-- Super-admin pour Ahmed Dendani (si le compte existe deja)
UPDATE users SET is_super_admin = TRUE WHERE email = 'ahmed@dendani.com';

-- 6. Row-Level Security (enforce strict par tenant sauf si session var app.is_super_admin='on')
ALTER TABLE tasks           ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_memory  ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tasks_tenant_isolation ON tasks;
CREATE POLICY tasks_tenant_isolation ON tasks
  USING (
    current_setting('app.is_super_admin', TRUE) = 'on'
    OR tenant_id = COALESCE(
         NULLIF(current_setting('app.tenant_id', TRUE), '')::uuid,
         '00000000-0000-0000-0000-000000000000'::uuid
       )
  );

DROP POLICY IF EXISTS project_memory_tenant_isolation ON project_memory;
CREATE POLICY project_memory_tenant_isolation ON project_memory
  USING (
    current_setting('app.is_super_admin', TRUE) = 'on'
    OR tenant_id = COALESCE(
         NULLIF(current_setting('app.tenant_id', TRUE), '')::uuid,
         '00000000-0000-0000-0000-000000000000'::uuid
       )
  );

-- IMPORTANT : `uba` est SUPERUSER (cree par docker-compose via POSTGRES_USER)
-- et bypasse donc RLS par design Postgres. Pour que la policy s'applique en
-- production, connecter l'app via un role non-superuser. On le provisionne :
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='uba_app') THEN
        CREATE ROLE uba_app NOINHERIT LOGIN PASSWORD 'uba_app';
    END IF;
END $$;

GRANT CONNECT ON DATABASE uba TO uba_app;
GRANT USAGE ON SCHEMA public TO uba_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO uba_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO uba_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO uba_app;

-- FORCE ROW LEVEL SECURITY : applique la policy meme aux OWNER
-- (mais ne peut rien sur les SUPERUSER Postgres, ceux-ci restent a bypass).
ALTER TABLE tasks           FORCE ROW LEVEL SECURITY;
ALTER TABLE project_memory  FORCE ROW LEVEL SECURITY;
