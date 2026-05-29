-- ============================================================
-- 001_initial.sql - Migration initiale PostgreSQL 16
-- Usine Bombe Atomique - Groupe Dendani
-- Conforme CDC v3.0 Ch.6
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- TABLE: users
-- ============================================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'operator'
        CHECK (role IN ('admin', 'operator', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: sessions
-- ============================================================
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'completed', 'error', 'archived')),
    message_count INTEGER NOT NULL DEFAULT 0,
    total_tokens BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: tasks
-- ============================================================
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    prompt TEXT NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'analyzing', 'planning',
                          'distributing', 'executing', 'validating',
                          'reworking', 'completed', 'failed', 'cancelled')),
    priority VARCHAR(20) NOT NULL DEFAULT 'high'
        CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    intent_json JSONB,
    plan_json JSONB,
    validation_score DECIMAL(10,6) DEFAULT 0,
    rework_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: agent_executions
-- ============================================================
CREATE TABLE agent_executions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id VARCHAR(100) NOT NULL,
    agent_name VARCHAR(200) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'success',
                          'failed', 'timeout', 'skipped')),
    inputs_json JSONB,
    output_json JSONB,
    error_message TEXT,
    duration_ms DECIMAL(12,2),
    attempt_number INTEGER NOT NULL DEFAULT 1,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: validation_logs
-- ============================================================
CREATE TABLE validation_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    level_number INTEGER NOT NULL CHECK (level_number BETWEEN 1 AND 9),
    level_name VARCHAR(200) NOT NULL,
    score DECIMAL(10,6) NOT NULL DEFAULT 0,
    passed BOOLEAN NOT NULL DEFAULT FALSE,
    details TEXT,
    issues_json JSONB DEFAULT '[]'::jsonb,
    rework_iteration INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: artifacts
-- ============================================================
CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    filename VARCHAR(500) NOT NULL,
    path VARCHAR(1000) NOT NULL,
    type VARCHAR(50) NOT NULL
        CHECK (type IN ('source_code', 'config', 'migration',
                        'test', 'documentation', 'docker', 'terraform')),
    language VARCHAR(50),
    size_bytes BIGINT NOT NULL DEFAULT 0,
    checksum_sha256 VARCHAR(64) NOT NULL,
    content TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: audit_logs
-- ============================================================
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    details_json JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- TABLE: api_usage
-- ============================================================
CREATE TABLE api_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id),
    agent_id VARCHAR(100),
    provider VARCHAR(50) NOT NULL DEFAULT 'anthropic',
    model VARCHAR(100) NOT NULL,
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_tasks_session ON tasks(session_id);
CREATE INDEX idx_tasks_user ON tasks(user_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);
CREATE INDEX idx_agent_exec_task ON agent_executions(task_id);
CREATE INDEX idx_agent_exec_agent ON agent_executions(agent_id);
CREATE INDEX idx_validation_task ON validation_logs(task_id);
CREATE INDEX idx_artifacts_task ON artifacts(task_id);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX idx_api_usage_task ON api_usage(task_id);
CREATE INDEX idx_api_usage_created ON api_usage(created_at DESC);

-- ============================================================
-- TRIGGERS: updated_at auto
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_sessions_updated BEFORE UPDATE ON sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_tasks_updated BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- VUE MATERIALISEE: Metriques Agent
-- ============================================================
CREATE MATERIALIZED VIEW mv_agent_metrics AS
SELECT
    agent_id,
    agent_name,
    COUNT(*) AS total_executions,
    COUNT(*) FILTER (WHERE status = 'success') AS successes,
    COUNT(*) FILTER (WHERE status = 'failed') AS failures,
    ROUND(AVG(duration_ms)::numeric, 2) AS avg_duration_ms,
    ROUND(
        (COUNT(*) FILTER (WHERE status = 'success')::numeric
         / NULLIF(COUNT(*), 0) * 100), 2
    ) AS success_rate_pct,
    MAX(created_at) AS last_execution
FROM agent_executions
GROUP BY agent_id, agent_name;

CREATE UNIQUE INDEX idx_mv_agent_metrics ON mv_agent_metrics(agent_id);
-- ============================================================
-- 002_memory_layer.sql - V3 Apprenante
-- 4 tables : project_memory, error_catalog, agent_benchmarks, prompt_variants
-- ============================================================

CREATE TABLE IF NOT EXISTS project_memory (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID UNIQUE REFERENCES tasks(id) ON DELETE CASCADE,
    spec_excerpt TEXT NOT NULL,
    domain_tags TEXT[] NOT NULL DEFAULT '{}',
    artifacts_count INTEGER NOT NULL DEFAULT 0,
    verdict VARCHAR(30) NOT NULL,
    validation_score DECIMAL(10,6) NOT NULL DEFAULT 0,
    confidence_composite DECIMAL(10,6) NOT NULL DEFAULT 0,
    confidence_label VARCHAR(20) NOT NULL DEFAULT 'unknown',
    total_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0,
    duration_ms BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pm_created   ON project_memory(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_verdict   ON project_memory(verdict);
CREATE INDEX IF NOT EXISTS idx_pm_tags_gin  ON project_memory USING GIN (domain_tags);

CREATE TABLE IF NOT EXISTS error_catalog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id VARCHAR(100) NOT NULL,
    signature VARCHAR(64) NOT NULL,
    error_type VARCHAR(120) NOT NULL,
    sample_message TEXT,
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id, signature)
);

CREATE INDEX IF NOT EXISTS idx_ec_agent ON error_catalog(agent_id);
CREATE INDEX IF NOT EXISTS idx_ec_last  ON error_catalog(last_seen_at DESC);

CREATE TABLE IF NOT EXISTS agent_benchmarks (
    agent_id VARCHAR(100) PRIMARY KEY,
    agent_name VARCHAR(200) NOT NULL,
    executions INTEGER NOT NULL DEFAULT 0,
    successes INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    total_duration_ms BIGINT NOT NULL DEFAULT 0,
    total_cost_usd DECIMAL(12,6) NOT NULL DEFAULT 0,
    avg_score DECIMAL(10,6) NOT NULL DEFAULT 0,
    score_samples INTEGER NOT NULL DEFAULT 0,
    last_update TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prompt_variants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_id VARCHAR(100) NOT NULL,
    variant_name VARCHAR(100) NOT NULL,
    system_prompt TEXT NOT NULL,
    weight DECIMAL(6,4) NOT NULL DEFAULT 0.5,
    executions INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    score_samples INTEGER NOT NULL DEFAULT 0,
    avg_score DECIMAL(10,6) NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id, variant_name)
);

CREATE INDEX IF NOT EXISTS idx_pv_agent_active ON prompt_variants(agent_id) WHERE is_active;

-- Seed initial : deux variantes de system_prompt pour agent-01-claude-code
INSERT INTO prompt_variants (agent_id, variant_name, system_prompt, weight)
VALUES
  ('agent-01-claude-code', 'strict_v1',
   'Tu es un generateur de code senior. A partir d''une specification, tu produis un projet Python/FastAPI minimal et fonctionnel. Reponds UNIQUEMENT avec un JSON valide : {"files": {"<chemin relatif>": "<contenu texte>", ...}}. Contraintes : code ruff-clean, tests pytest dans tests/, requirements.txt, README.md.',
   0.5),
  ('agent-01-claude-code', 'pragmatic_v2',
   'Tu es un ingenieur logiciel senior. Tu livres un projet Python/FastAPI complet et robuste a partir d''une specification metier. Produis UNIQUEMENT un JSON {"files": {...}}. Inclus typage strict, tests pytest couvrant les regles metier, Dockerfile multi-stage non-root, README avec exemples curl. Aucun commentaire superflu.',
   0.5)
ON CONFLICT (agent_id, variant_name) DO NOTHING;
-- ============================================================
-- 003_auto_optimization.sql - V4 Auto-Optimisante
-- 4 tables : validation_thresholds, agent_marketplace,
--            improvement_backlog, pending_questions
-- ============================================================

CREATE TABLE IF NOT EXISTS validation_thresholds (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scope VARCHAR(80) NOT NULL,  -- 'global' ou 'domain:<tag>'
    pass_min DECIMAL(6,4) NOT NULL DEFAULT 0.85,
    cpass_min DECIMAL(6,4) NOT NULL DEFAULT 0.70,
    soft_fail_min DECIMAL(6,4) NOT NULL DEFAULT 0.50,
    sample_count INTEGER NOT NULL DEFAULT 0,
    last_recomputed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (scope)
);

INSERT INTO validation_thresholds (scope) VALUES ('global') ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS agent_marketplace (
    agent_id VARCHAR(100) PRIMARY KEY,
    agent_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    status VARCHAR(20) NOT NULL DEFAULT 'healthy'
        CHECK (status IN ('healthy', 'at_risk', 'deprecated', 'stub', 'new')),
    rank INTEGER,
    reason TEXT,
    last_change TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS improvement_backlog (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signature VARCHAR(64) UNIQUE NOT NULL,
    category VARCHAR(40) NOT NULL
        CHECK (category IN ('error_pattern','agent_weak','calibration',
                            'coverage_gap','cost','architecture')),
    priority VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (priority IN ('low','medium','high','critical')),
    title VARCHAR(240) NOT NULL,
    rationale TEXT NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','acknowledged','in_progress','shipped','rejected')),
    occurrences INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backlog_status ON improvement_backlog(status, priority DESC);

CREATE TABLE IF NOT EXISTS pending_questions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE UNIQUE,
    question TEXT NOT NULL,
    category VARCHAR(40) NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open','answered','dismissed')),
    answer TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    answered_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pq_status ON pending_questions(status, created_at DESC);

-- Etend la CHECK constraint tasks.status pour autoriser 'waiting_input'
ALTER TABLE tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_status_check
    CHECK (status IN ('pending','analyzing','planning','distributing',
                      'executing','validating','reworking',
                      'completed','failed','cancelled','waiting_input'));
-- ============================================================
-- 004_evidence_ledger.sql - Journal immuable chaine SHA-256
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_ledger (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    actor VARCHAR(120) NOT NULL,
    kind VARCHAR(40) NOT NULL
        CHECK (kind IN ('decision','artifact','test','override',
                        'arbiter','contradiction','hypothesis',
                        'challenger','repair','contract_violation')),
    payload_hash CHAR(64) NOT NULL,
    prev_hash CHAR(64) NOT NULL,
    chain_hash CHAR(64) NOT NULL UNIQUE,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_task    ON evidence_ledger(task_id);
CREATE INDEX IF NOT EXISTS idx_evidence_kind    ON evidence_ledger(kind);
CREATE INDEX IF NOT EXISTS idx_evidence_created ON evidence_ledger(created_at DESC);

-- Trigger append-only : aucune UPDATE/DELETE autorisee
CREATE OR REPLACE FUNCTION evidence_ledger_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evidence_ledger is append-only (no % allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_block_update ON evidence_ledger;
CREATE TRIGGER trg_evidence_block_update
    BEFORE UPDATE ON evidence_ledger
    FOR EACH ROW EXECUTE FUNCTION evidence_ledger_block_mutations();

DROP TRIGGER IF EXISTS trg_evidence_block_delete ON evidence_ledger;
CREATE TRIGGER trg_evidence_block_delete
    BEFORE DELETE ON evidence_ledger
    FOR EACH ROW EXECUTE FUNCTION evidence_ledger_block_mutations();

-- Pas de genesis row : la table demarre vide. Le premier event inscrit
-- via `evidence_ledger.record()` utilise GENESIS_HASH (0*64) comme prev_hash,
-- et la chaine grossit. `verify_chain()` rejoue depuis GENESIS_HASH.
-- ============================================================
-- 005_hypotheses_registry.sql - Hypotheses non resolues
-- ============================================================

CREATE TABLE IF NOT EXISTS hypotheses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    source VARCHAR(120) NOT NULL,
    owner VARCHAR(120),
    impact_si_faux TEXT NOT NULL DEFAULT '',
    plan_b TEXT NOT NULL DEFAULT '',
    statut VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (statut IN ('open','verified','refuted','accepted_risk','dropped')),
    severity VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low','medium','high','critical')),
    resolution_evidence_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_hypo_task   ON hypotheses(task_id);
CREATE INDEX IF NOT EXISTS idx_hypo_statut ON hypotheses(statut, severity DESC);
CREATE INDEX IF NOT EXISTS idx_hypo_source ON hypotheses(source);
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
-- ============================================================
-- 007_audit_events.sql - Event sourcing append-only, retention 7 ans
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    tenant_id UUID REFERENCES tenants(id),
    actor VARCHAR(200) NOT NULL,
    action VARCHAR(80) NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retention_until TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 years')
);

CREATE INDEX IF NOT EXISTS idx_audit_events_task     ON audit_events(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_tenant   ON audit_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_audit_events_actor    ON audit_events(actor);
CREATE INDEX IF NOT EXISTS idx_audit_events_action   ON audit_events(action);
CREATE INDEX IF NOT EXISTS idx_audit_events_created  ON audit_events(created_at DESC);

-- Append-only : pas de UPDATE / DELETE (retention 7 ans legale)
CREATE OR REPLACE FUNCTION audit_events_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_events is append-only (retention 7 ans - no % allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_events_block_update ON audit_events;
CREATE TRIGGER trg_audit_events_block_update
    BEFORE UPDATE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutations();

DROP TRIGGER IF EXISTS trg_audit_events_block_delete ON audit_events;
CREATE TRIGGER trg_audit_events_block_delete
    BEFORE DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION audit_events_block_mutations();
-- ============================================================
-- 008_v42_mega.sql - V4.2 : 9 nouvelles tables pour 24 upgrades
-- ============================================================

-- 35 : Defect Taxonomy
CREATE TABLE IF NOT EXISTS defect_taxonomy (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    nature VARCHAR(30) NOT NULL
        CHECK (nature IN ('structure','logique','securite','conformite','performance')),
    gravite VARCHAR(20) NOT NULL
        CHECK (gravite IN ('info','mineure','bloquante','vitale')),
    rayon_impact VARCHAR(20) NOT NULL DEFAULT 'local'
        CHECK (rayon_impact IN ('local','module','service','system')),
    recurrence INTEGER NOT NULL DEFAULT 1,
    signature VARCHAR(64) NOT NULL,
    title VARCHAR(240) NOT NULL,
    details TEXT,
    correction_patch_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (task_id, signature)
);
CREATE INDEX IF NOT EXISTS idx_defect_nature ON defect_taxonomy(nature, gravite);
CREATE INDEX IF NOT EXISTS idx_defect_task   ON defect_taxonomy(task_id);

-- 30 : Regles DZ parametrables en base (versionnees)
CREATE TABLE IF NOT EXISTS dz_rules_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_code VARCHAR(40) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    label VARCHAR(240) NOT NULL,
    regex_positive TEXT,
    regex_negative TEXT,
    threshold_min DECIMAL(10,6),
    threshold_max DECIMAL(10,6),
    severity VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low','medium','high','critical')),
    created_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_code, version)
);

INSERT INTO dz_rules_config (rule_code, version, label, regex_positive, threshold_min, threshold_max, severity) VALUES
  ('R1_TVA19',   1, 'TVA 19% mentionnee + constante',      '\bTVA\b.*0\.19|\b19\s*%',      0.19, 0.19, 'high'),
  ('R2_TAP2',    1, 'TAP 2% mentionnee + constante',       '\bTAP\b.*0\.02|\b2\s*%',       0.02, 0.02, 'high'),
  ('R3_CNAS',    1, 'CNAS 9% salarie + 26% employeur',     '\b0\.09\b.*\b0\.26\b',          0.09, 0.26, 'high'),
  ('R4_IRG',     1, 'IRG progressif 4 tranches',           'IRG',                            NULL, NULL, 'high'),
  ('R5_NIN18',   1, 'NIN 18 chiffres',                      '\bnin\b.*\b18\b',                 18.0, 18.0, 'medium'),
  ('R6_DZD',     1, 'Devise DZD / Dinar',                  '\bDZD\b|\bDinar',                NULL, NULL, 'medium'),
  ('R7_NoForeignRegs', 1, 'Pas de regs non-DZ exclusives', NULL,                              NULL, NULL, 'critical'),
  ('R8_VEFA_Paliers', 1, 'Paliers VEFA 20/15/35/25/5',     '20.*15.*35.*25.*5',               NULL, NULL, 'high')
ON CONFLICT (rule_code, version) DO NOTHING;

-- 37 : Pipeline innovation
CREATE TABLE IF NOT EXISTS innovation_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind VARCHAR(30) NOT NULL
        CHECK (kind IN ('model','library','tool','strategy')),
    name VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    stage VARCHAR(30) NOT NULL DEFAULT 'scout'
        CHECK (stage IN ('scout','qualification','benchmark',
                          'risk_review','pending_approval',
                          'staged','active','rollback','rejected')),
    benchmark_score DECIMAL(5,3),
    risk_notes TEXT,
    approved_by VARCHAR(120),
    approved_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kind, name)
);

-- 24 : Cache semantique (embedding stocke en JSONB si pgvector absent)
CREATE TABLE IF NOT EXISTS semantic_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    spec_hash CHAR(64) NOT NULL UNIQUE,
    spec_excerpt TEXT NOT NULL,
    fingerprint JSONB NOT NULL,     -- representation numerique simple (fallback pgvector)
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    artifact_count INTEGER NOT NULL DEFAULT 0,
    reuse_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_hit_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_semcache_last ON semantic_cache(last_hit_at DESC);

-- 28 : DAG checkpoints (miroir Redis pour le cas crash - persistant)
CREATE TABLE IF NOT EXISTS dag_checkpoints (
    task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    completed_waves JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_wave_index INTEGER NOT NULL DEFAULT -1,
    agent_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 36 : Truth KPI snapshots (aggregation periodique)
CREATE TABLE IF NOT EXISTS truth_kpi_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    defect_escape_rate DECIMAL(6,4),
    false_pass_rate DECIMAL(6,4),
    false_fail_rate DECIMAL(6,4),
    confidence_calibration_error DECIMAL(6,4),
    revalidation_completeness_rate DECIMAL(6,4),
    patch_recurrence_rate DECIMAL(6,4),
    runtime_contradiction_rate DECIMAL(6,4),
    proof_coverage_rate DECIMAL(6,4),
    samples INTEGER NOT NULL DEFAULT 0
);

-- 29 : Journal quorum judge
CREATE TABLE IF NOT EXISTS quorum_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    judge_1_verdict VARCHAR(20) NOT NULL,
    judge_2_verdict VARCHAR(20) NOT NULL,
    judge_3_verdict VARCHAR(20) NOT NULL,
    final_verdict VARCHAR(20) NOT NULL,
    has_disagreement BOOLEAN NOT NULL DEFAULT FALSE,
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quorum_disagree ON quorum_decisions(has_disagreement);

-- 14 : Rollback automatique
CREATE TABLE IF NOT EXISTS rollback_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    trigger_reason VARCHAR(60) NOT NULL,
    confidence_before DECIMAL(6,4),
    confidence_after DECIMAL(6,4),
    artifact_version_before VARCHAR(64),
    artifact_version_after VARCHAR(64),
    auto_triggered BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 23 : Audit reseau sandbox
CREATE TABLE IF NOT EXISTS network_audit_log (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    sandbox_id VARCHAR(80) NOT NULL,
    outbound_attempts INTEGER NOT NULL DEFAULT 0,
    violations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    verdict VARCHAR(20) NOT NULL DEFAULT 'clean'
        CHECK (verdict IN ('clean','violated','inconclusive')),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- ============================================================
-- 009_compliance_matrix.sql - V4.3 matrice exigences <-> preuves
-- ============================================================

CREATE TABLE IF NOT EXISTS compliance_matrix (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    requirement_code VARCHAR(80) NOT NULL,
    requirement_label TEXT NOT NULL,
    test_ref VARCHAR(240),
    proof_ref VARCHAR(240),           -- ex: evidence_ledger.event_id / artifact path
    statut VARCHAR(20) NOT NULL DEFAULT 'open'
        CHECK (statut IN ('open','in_progress','satisfied','waived','failed')),
    responsable VARCHAR(120),
    severity VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low','medium','high','critical')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (task_id, requirement_code)
);

CREATE INDEX IF NOT EXISTS idx_compliance_task ON compliance_matrix(task_id);
CREATE INDEX IF NOT EXISTS idx_compliance_statut ON compliance_matrix(statut, severity DESC);
-- ============================================================
-- 010_tool_registry_pgvector.sql - V4.3 registry SaaS + pgvector
-- ============================================================

-- 1. pgvector (image pgvector/pgvector:pg16 requise)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Registre des outils externes connectes
CREATE TABLE IF NOT EXISTS tool_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tool_id VARCHAR(60) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    tool_type VARCHAR(30) NOT NULL
        CHECK (tool_type IN ('saas','self_hosted','mcp','api','cli')),
    url VARCHAR(500),
    api_key_vault_path VARCHAR(200),
    status VARCHAR(30) NOT NULL DEFAULT 'pending_setup'
        CHECK (status IN ('connected','disconnected','pending_setup',
                          'needs_user_input','broken','deprecated')),
    capabilities JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_health_at TIMESTAMPTZ,
    last_health_status VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    connected_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tool_status ON tool_registry(status);

-- 3. Demandes d'input utilisateur (lies aux outils pendant provisioning)
CREATE TABLE IF NOT EXISTS pending_user_inputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    tool_id VARCHAR(60),
    request_kind VARCHAR(40) NOT NULL
        CHECK (request_kind IN ('email','password','otp','captcha','payment',
                                'api_key','custom','two_factor')),
    fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    context TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'awaiting'
        CHECK (status IN ('awaiting','submitted','expired','cancelled')),
    submission_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '1 hour'
);

CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_user_inputs(status);
CREATE INDEX IF NOT EXISTS idx_pending_task ON pending_user_inputs(task_id);

-- 4. Enrichir semantic_cache avec une vraie colonne vector (V4.2 JSONB fallback reste)
ALTER TABLE semantic_cache
    ADD COLUMN IF NOT EXISTS embedding vector(128);
CREATE INDEX IF NOT EXISTS idx_semcache_embedding
    ON semantic_cache USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);
-- ============================================================
-- 011_promotion_runtime.sql - V4.4
-- Decision Router (log), Promotion Progressive, Runtime Mesh
-- ============================================================

CREATE TABLE IF NOT EXISTS decision_router_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    route VARCHAR(30) NOT NULL
        CHECK (route IN ('robust_success','partial_success',
                         'correctable_fail','critical_fail')),
    verdict VARCHAR(20) NOT NULL,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    invariants_violated JSONB NOT NULL DEFAULT '[]'::jsonb,
    defect_classes JSONB NOT NULL DEFAULT '[]'::jsonb,
    actions_taken JSONB NOT NULL DEFAULT '[]'::jsonb,
    rationale TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_dr_task ON decision_router_log(task_id);
CREATE INDEX IF NOT EXISTS idx_dr_route ON decision_router_log(route, created_at DESC);


CREATE TABLE IF NOT EXISTS promotion_stages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    artifact_version CHAR(64) NOT NULL,
    stage VARCHAR(20) NOT NULL
        CHECK (stage IN ('build','staging','canary','production','rolled_back')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','in_progress','passed','failed','skipped','rolled_back')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    evidence_event_id UUID,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    rollback_reason TEXT,
    UNIQUE (task_id, artifact_version, stage)
);
CREATE INDEX IF NOT EXISTS idx_promo_task ON promotion_stages(task_id);
CREATE INDEX IF NOT EXISTS idx_promo_stage ON promotion_stages(stage, status);


CREATE TABLE IF NOT EXISTS runtime_metrics (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    artifact_version CHAR(64),
    target VARCHAR(120) NOT NULL,       -- ex: service URL ou nom de container
    metric VARCHAR(40) NOT NULL,        -- latency_p95_ms | error_rate | cpu_pct | mem_mb | health
    value DECIMAL(14,4) NOT NULL,
    baseline DECIMAL(14,4),
    drift_pct DECIMAL(10,4),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_metrics_target_time ON runtime_metrics(target, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_task ON runtime_metrics(task_id);


CREATE TABLE IF NOT EXISTS runtime_baselines (
    target VARCHAR(120) NOT NULL,
    metric VARCHAR(40) NOT NULL,
    value DECIMAL(14,4) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (target, metric)
);


CREATE TABLE IF NOT EXISTS incident_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    incident_kind VARCHAR(40) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'high'
        CHECK (severity IN ('low','medium','high','critical')),
    title VARCHAR(240) NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    human_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_incident_ack ON incident_log(human_acknowledged, created_at DESC);
-- ============================================================
-- 012_ahmed_inbox.sql - V4.8
-- Etend pending_user_inputs avec form_type A/B/C (doctrine MIT Senior)
-- ============================================================

-- Ajout des colonnes si pas deja presentes
ALTER TABLE pending_user_inputs
    ADD COLUMN IF NOT EXISTS form_type CHAR(1);

-- CHECK constraint flexible : A/B/C ou NULL pour les entrees V4.3 legacy
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_form_type_abc'
    ) THEN
        ALTER TABLE pending_user_inputs
            ADD CONSTRAINT chk_form_type_abc
            CHECK (form_type IS NULL OR form_type IN ('A','B','C'));
    END IF;
END $$;

ALTER TABLE pending_user_inputs
    ADD COLUMN IF NOT EXISTS service_name VARCHAR(120),
    ADD COLUMN IF NOT EXISTS why TEXT,
    ADD COLUMN IF NOT EXISTS cost_amount VARCHAR(80),
    ADD COLUMN IF NOT EXISTS cost_currency VARCHAR(10),
    ADD COLUMN IF NOT EXISTS payment_url VARCHAR(1000),
    ADD COLUMN IF NOT EXISTS free_alternative BOOLEAN,
    ADD COLUMN IF NOT EXISTS question_id VARCHAR(40),
    ADD COLUMN IF NOT EXISTS suggested_answer TEXT,
    ADD COLUMN IF NOT EXISTS criticality VARCHAR(10) DEFAULT 'medium'
        CHECK (criticality IS NULL OR criticality IN ('low','medium','high','critical'));

CREATE INDEX IF NOT EXISTS idx_pending_form_type
    ON pending_user_inputs(form_type, status, created_at DESC);

-- Journal des tentatives de demande NON-ABC (bloquees par le routeur)
CREATE TABLE IF NOT EXISTS blocked_user_asks (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    actor VARCHAR(120) NOT NULL,
    rejected_request JSONB NOT NULL,
    reason TEXT NOT NULL,
    auto_resolution JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_blocked_task ON blocked_user_asks(task_id);

-- Snapshot des metriques systeme (meta-optimizer)
CREATE TABLE IF NOT EXISTS meta_metrics_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    projects_last_7d INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms INTEGER NOT NULL DEFAULT 0,
    rework_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    avg_cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    verdict_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    degraded_metrics JSONB NOT NULL DEFAULT '[]'::jsonb
);
-- ============================================================
-- 013_autonomy_c_subtypes.sql - V5.1
-- Decompose Type C en 6 sous-types C1..C6 (vraies zones d'ambiguite)
-- + Registre d'ambiguite + lease permissions + hard boundaries
-- ============================================================

-- Type C split : C1..C6
ALTER TABLE pending_user_inputs
    ADD COLUMN IF NOT EXISTS c_sub_type VARCHAR(4);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_c_sub_type') THEN
        ALTER TABLE pending_user_inputs
            ADD CONSTRAINT chk_c_sub_type
            CHECK (c_sub_type IS NULL OR c_sub_type IN
                   ('C1','C2','C3','C4','C5','C6'));
    END IF;
END $$;

-- Ambiguity ledger : trace chaque resolution d'ambiguite
CREATE TABLE IF NOT EXISTS ambiguity_ledger (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    correlation_id VARCHAR(64),
    level INTEGER NOT NULL,          -- 1=doc/repo, 2=industry, 3=bounded sim, 4=ask
    resolved BOOLEAN NOT NULL,
    kind VARCHAR(30) NOT NULL,       -- semantic|factual|value|strategic|false|self_induced
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ask_skipped BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ambiguity_task
    ON ambiguity_ledger(task_id, created_at DESC);

-- Permission leases : scope + cap + duration + auto-expiry
CREATE TABLE IF NOT EXISTS permission_leases (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    scope VARCHAR(120) NOT NULL,      -- ex: "payment.datadog"
    cap_amount DECIMAL(14,4),
    cap_currency VARCHAR(10),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    usage_count INTEGER NOT NULL DEFAULT 0,
    usage_cap INTEGER NOT NULL DEFAULT 1,
    granter VARCHAR(120) NOT NULL DEFAULT 'ahmed'
);
CREATE INDEX IF NOT EXISTS idx_lease_scope_active
    ON permission_leases(scope, expires_at)
    WHERE revoked_at IS NULL;

-- Hard boundaries : scopes qui DOIVENT escalader (paiement, rollback prod, RGPD...)
CREATE TABLE IF NOT EXISTS hard_boundary_registry (
    scope VARCHAR(120) PRIMARY KEY,
    description TEXT NOT NULL,
    requires_type VARCHAR(1) NOT NULL
        CHECK (requires_type IN ('A','B','C')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO hard_boundary_registry(scope, description, requires_type) VALUES
    ('payment.any', 'Tout paiement direct vers un fournisseur', 'B'),
    ('credentials.new_account', 'Creation compte externe exigeant identite', 'A'),
    ('prod.rollback_last_resort', 'Rollback prod apres epuisement des patches', 'C'),
    ('gdpr.waiver', 'Derogation donnee personnelle RGPD', 'C'),
    ('dendani.reputation_risk', 'Action a risque reputationnel Dendani', 'C')
ON CONFLICT (scope) DO NOTHING;
-- ============================================================
-- 014_autonomy_metrics_v51.sql - V5.1 BLOC 13
-- KPIs autonomie : action_rate, ahmed_load, calibration, chaos...
-- ============================================================

CREATE TABLE IF NOT EXISTS autonomy_metrics (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_hours INTEGER NOT NULL DEFAULT 168,
    -- Action metrics
    autonomy_action_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    autonomy_weighted_by_criticity DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Avoidable escalations
    avoidable_escalation_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    escalation_precision DECIMAL(6,4) NOT NULL DEFAULT 0,
    questions_per_escalation DECIMAL(6,3) NOT NULL DEFAULT 0,
    -- Ahmed load
    ahmed_cognitive_load_minutes_per_project DECIMAL(10,2) NOT NULL DEFAULT 0,
    ahmed_interruptions_per_project DECIMAL(6,2) NOT NULL DEFAULT 0,
    autonomous_continuation_rate_after_block DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Calibration
    confidence_calibration_score DECIMAL(6,4) NOT NULL DEFAULT 0,
    patch_success_by_type JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Distribution
    c_sub_type_distribution JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Chaos / resilience
    chaos_pass_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    mean_time_to_self_heal_seconds INTEGER NOT NULL DEFAULT 0,
    -- Freshness
    artifact_freshness_median_minutes INTEGER NOT NULL DEFAULT 0,
    stale_data_incidents INTEGER NOT NULL DEFAULT 0,
    -- Permission leases
    active_leases INTEGER NOT NULL DEFAULT 0,
    lease_cap_violations INTEGER NOT NULL DEFAULT 0,
    -- Human load budget
    human_load_budget_used_pct DECIMAL(6,4) NOT NULL DEFAULT 0,
    -- Raw details
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_autonomy_metrics_captured
    ON autonomy_metrics(captured_at DESC);

-- Chaos runs journal
CREATE TABLE IF NOT EXISTS autonomy_chaos_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario VARCHAR(120) NOT NULL,
    passed BOOLEAN NOT NULL,
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    self_healed BOOLEAN NOT NULL DEFAULT FALSE,
    triggered_escalation BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chaos_runs_created
    ON autonomy_chaos_runs(created_at DESC);

-- Correlation id registry : trace un artefact de bout en bout
CREATE TABLE IF NOT EXISTS correlation_ledger (
    correlation_id VARCHAR(64) PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    origin VARCHAR(60) NOT NULL,      -- ex: "ahmed_inbox", "agent_dag"
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    final_verdict VARCHAR(30),
    hop_count INTEGER NOT NULL DEFAULT 0
);

-- Intervention outcomes : apprentissage sur les vraies et fausses escalations
CREATE TABLE IF NOT EXISTS intervention_outcomes (
    id BIGSERIAL PRIMARY KEY,
    pending_request_id UUID,
    form_type CHAR(1) NOT NULL,
    c_sub_type VARCHAR(4),
    was_necessary BOOLEAN,            -- verdict retrospectif
    ahmed_response_ms INTEGER,
    autonomy_alternative TEXT,        -- ce qu'on aurait pu faire sans ahmed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_intervention_necessary
    ON intervention_outcomes(was_necessary, created_at DESC);

-- Negative escalation registry : patterns a ne PAS escalader
CREATE TABLE IF NOT EXISTS negative_escalation_registry (
    id BIGSERIAL PRIMARY KEY,
    signature VARCHAR(120) NOT NULL UNIQUE,
    description TEXT NOT NULL,
    example_request JSONB NOT NULL,
    resolution_hint TEXT NOT NULL,
    learned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    occurrences INTEGER NOT NULL DEFAULT 1
);

-- Human Necessity Proof : preuve structuree avant toute escalation
CREATE TABLE IF NOT EXISTS human_necessity_proofs (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    correlation_id VARCHAR(64),
    form_type CHAR(1) NOT NULL,
    c_sub_type VARCHAR(4),
    levels_tried JSONB NOT NULL DEFAULT '[]'::jsonb,
    counterfactual JSONB NOT NULL DEFAULT '{}'::jsonb,
    proof_hash VARCHAR(64) NOT NULL,
    verdict VARCHAR(20) NOT NULL,     -- proved|rejected
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_necessity_verdict
    ON human_necessity_proofs(verdict, created_at DESC);
-- ============================================================
-- 015_system_parameters.sql - V5.2 BLOC 2
-- Table system_parameters : regles PARAMETRIZABLE / LEARNABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS system_parameters (
    id BIGSERIAL PRIMARY KEY,
    parameter_key VARCHAR(120) NOT NULL,
    parameter_value JSONB NOT NULL,
    parameter_category VARCHAR(20) NOT NULL
        CHECK (parameter_category IN ('PARAMETRIZABLE','LEARNABLE')),
    allowed_min DECIMAL(18,6),
    allowed_max DECIMAL(18,6),
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    version INTEGER NOT NULL DEFAULT 1,
    changed_by VARCHAR(120) NOT NULL DEFAULT 'system',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    justification TEXT,
    rollback_value JSONB,
    UNIQUE (parameter_key, version)
);
CREATE INDEX IF NOT EXISTS idx_system_params_key
    ON system_parameters(parameter_key, version DESC);

-- Vue pratique : derniere version active par cle
CREATE OR REPLACE VIEW system_parameters_current AS
SELECT DISTINCT ON (parameter_key)
    parameter_key, parameter_value, parameter_category,
    allowed_min, allowed_max, requires_approval,
    version, changed_by, changed_at, justification
FROM system_parameters
ORDER BY parameter_key, version DESC;

-- Seed PARAMETRIZABLE
INSERT INTO system_parameters(parameter_key, parameter_value,
    parameter_category, requires_approval, justification)
VALUES
  ('confidence.threshold.critical_fiscal', '0.95'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'seuil confiance pour calcul fiscal DZ'),
  ('confidence.threshold.security', '0.90'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'seuil confiance securite'),
  ('confidence.threshold.ui_ux', '0.75'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'seuil UI/UX'),
  ('agent.timeout.default_seconds', '180'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'timeout par defaut agents'),
  ('budget.tokens.per_task', '60000'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'budget tokens par tache'),
  ('rework.max_iterations', '3'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'max iterations rework'),
  ('lease.ttl.default_days', '30'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'TTL lease par defaut')
ON CONFLICT (parameter_key, version) DO NOTHING;

-- Seed LEARNABLE avec bounds durs
INSERT INTO system_parameters(parameter_key, parameter_value,
    parameter_category, allowed_min, allowed_max, requires_approval,
    justification)
VALUES
  ('scoring.weight.correctness', '0.25'::jsonb,
   'LEARNABLE', 0.15, 0.40, FALSE,
   'poids correctness dans composite'),
  ('scoring.weight.quality', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.25, FALSE,
   'poids quality'),
  ('scoring.weight.coverage', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.25, FALSE,
   'poids coverage'),
  ('scoring.weight.security', '0.20'::jsonb,
   'LEARNABLE', 0.10, 0.35, FALSE,
   'poids security'),
  ('scoring.weight.conformity', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.30, FALSE,
   'poids conformity (DZ)'),
  ('scoring.weight.maintainability', '0.10'::jsonb,
   'LEARNABLE', 0.05, 0.20, FALSE,
   'poids maintainability'),
  ('pass_min', '0.80'::jsonb,
   'LEARNABLE', 0.75, 0.90, TRUE,
   'seuil pass_min'),
  ('cpass_min', '0.70'::jsonb,
   'LEARNABLE', 0.60, 0.80, TRUE,
   'seuil conditional pass_min'),
  ('soft_fail_min', '0.50'::jsonb,
   'LEARNABLE', 0.40, 0.70, TRUE,
   'seuil soft_fail_min')
ON CONFLICT (parameter_key, version) DO NOTHING;
-- ============================================================
-- 016_decisions_audit.sql - V5.2 BLOC 6
-- Table decisions_audit : trace immuable de chaque decision reasoning
-- ============================================================

CREATE TABLE IF NOT EXISTS decisions_audit (
    id BIGSERIAL PRIMARY KEY,
    decision_id UUID NOT NULL DEFAULT uuid_generate_v4() UNIQUE,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    context_hash CHAR(64) NOT NULL,
    domain VARCHAR(80) NOT NULL,
    category VARCHAR(20) NOT NULL
        CHECK (category IN ('HARDCODED_FROZEN','PARAMETRIZABLE',
                             'LEARNABLE','REASONABLE')),
    chosen_value JSONB NOT NULL,
    alternatives_considered JSONB NOT NULL DEFAULT '[]'::jsonb,
    reasoning_trace TEXT NOT NULL,
    confidence_score DECIMAL(6,4) NOT NULL DEFAULT 0,
    bounds_respected BOOLEAN NOT NULL DEFAULT TRUE,
    invariants_checked JSONB NOT NULL DEFAULT '[]'::jsonb,
    quality_kernel_validation JSONB,
    actor VARCHAR(120) NOT NULL,
    correlation_id VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    rollback_state JSONB,
    retention_until TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '7 years')
);

CREATE INDEX IF NOT EXISTS idx_decisions_task
    ON decisions_audit(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_domain
    ON decisions_audit(domain, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_category
    ON decisions_audit(category, created_at DESC);

-- Trigger append-only (identique a audit_events)
CREATE OR REPLACE FUNCTION decisions_audit_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'decisions_audit is append-only (retention 7 ans, no UPDATE/DELETE)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decisions_block_update ON decisions_audit;
CREATE TRIGGER trg_decisions_block_update
    BEFORE UPDATE ON decisions_audit
    FOR EACH ROW EXECUTE FUNCTION decisions_audit_block_mutations();

DROP TRIGGER IF EXISTS trg_decisions_block_delete ON decisions_audit;
CREATE TRIGGER trg_decisions_block_delete
    BEFORE DELETE ON decisions_audit
    FOR EACH ROW EXECUTE FUNCTION decisions_audit_block_mutations();
-- ============================================================
-- 017_reasoning_promotions.sql - V5.2 BLOC 8
-- Table reasoning_promotions : shadow -> limited -> full
-- ============================================================

CREATE TABLE IF NOT EXISTS reasoning_promotions (
    id BIGSERIAL PRIMARY KEY,
    rule_key VARCHAR(120) NOT NULL,
    phase VARCHAR(20) NOT NULL
        CHECK (phase IN ('shadow','limited','full','rejected','rolled_back')),
    sample_size INTEGER NOT NULL DEFAULT 0,
    divergence_rate DECIMAL(6,4),
    quality_delta DECIMAL(6,4),
    cost_delta DECIMAL(10,6),
    invariants_violated INTEGER NOT NULL DEFAULT 0,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    promoted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    promoted_by VARCHAR(120) NOT NULL DEFAULT 'canary_engine'
);
CREATE INDEX IF NOT EXISTS idx_reasoning_promo_rule
    ON reasoning_promotions(rule_key, promoted_at DESC);

-- Journal derive detectee
CREATE TABLE IF NOT EXISTS drift_alerts (
    id BIGSERIAL PRIMARY KEY,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    drift_kind VARCHAR(40) NOT NULL
        CHECK (drift_kind IN ('statistical','invariant','performance','quality')),
    severity VARCHAR(20) NOT NULL
        CHECK (severity IN ('warning','warning_strong','critical')),
    metric VARCHAR(120) NOT NULL,
    baseline_value DECIMAL(12,4),
    current_value DECIMAL(12,4),
    deviation_pct DECIMAL(8,4),
    auto_action VARCHAR(80),     -- ex: 'pause_tuning', 'rollback'
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_drift_alerts_severity
    ON drift_alerts(severity, detected_at DESC);
-- ============================================================
-- 019_cognition_reasoning_traces.sql - V5.4 PARTIE 3
-- 15 tables reasoning_* + cognitive_decisions + benchmarks
-- Numerotee 019 (avant 020 CTC) pour coherence chronologique
-- meme si appliquee apres.
-- ============================================================

CREATE TABLE IF NOT EXISTS reasoning_traces (
    trace_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    session_id UUID,
    agent_id VARCHAR(120),
    problem_statement TEXT NOT NULL,
    problem_type VARCHAR(30) NOT NULL
        CHECK (problem_type IN ('simple','moderate','complex','creative',
                                 'sequential','ambiguous')),
    input_hash CHAR(64) NOT NULL,
    output_hash CHAR(64),
    rules_version VARCHAR(40) NOT NULL DEFAULT 'v5.4',
    model_version VARCHAR(40),
    technique_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_answer JSONB,
    final_confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    reasoning_fingerprint CHAR(64) NOT NULL,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_duration_ms INTEGER NOT NULL DEFAULT 0,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'in_progress'
        CHECK (status IN ('in_progress','completed','failed','killed','cached')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_rtr_task ON reasoning_traces(task_id);
CREATE INDEX IF NOT EXISTS idx_rtr_fingerprint ON reasoning_traces(reasoning_fingerprint);
CREATE INDEX IF NOT EXISTS idx_rtr_status ON reasoning_traces(status, created_at DESC);

CREATE TABLE IF NOT EXISTS reasoning_nodes (
    node_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    kind VARCHAR(20) NOT NULL
        CHECK (kind IN ('thought','action','observation','reflection','critique')),
    depth INTEGER NOT NULL DEFAULT 0,
    value DECIMAL(6,4),
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rnodes_trace ON reasoning_nodes(trace_id, depth);

CREATE TABLE IF NOT EXISTS reasoning_edges (
    edge_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    src_node UUID REFERENCES reasoning_nodes(node_id) ON DELETE CASCADE,
    dst_node UUID REFERENCES reasoning_nodes(node_id) ON DELETE CASCADE,
    edge_type VARCHAR(20) NOT NULL
        CHECK (edge_type IN ('supports','derives','contradicts','aggregates','refines')),
    weight DECIMAL(6,4) NOT NULL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_redges_trace ON reasoning_edges(trace_id);

CREATE TABLE IF NOT EXISTS chain_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    mode VARCHAR(30) NOT NULL
        CHECK (mode IN ('zero_shot','few_shot','program_aided',
                         'self_consistent','structured')),
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    intermediate_conclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    alternatives_rejected JSONB NOT NULL DEFAULT '[]'::jsonb,
    verification_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
    final_answer TEXT,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tree_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    strategy VARCHAR(20) NOT NULL
        CHECK (strategy IN ('dfs','bfs','best_first','mcts')),
    max_depth INTEGER NOT NULL,
    branching_factor INTEGER NOT NULL,
    nodes_generated INTEGER NOT NULL DEFAULT 0,
    nodes_pruned INTEGER NOT NULL DEFAULT 0,
    best_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_score DECIMAL(6,4) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS graph_traces (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    node_count INTEGER NOT NULL DEFAULT 0,
    edge_count INTEGER NOT NULL DEFAULT 0,
    contradictions JSONB NOT NULL DEFAULT '[]'::jsonb,
    convergences JSONB NOT NULL DEFAULT '[]'::jsonb,
    dominant_paths JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS debate_sessions (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    role_a VARCHAR(60) NOT NULL,
    role_b VARCHAR(60) NOT NULL,
    rounds INTEGER NOT NULL DEFAULT 0,
    devils_advocate_activated BOOLEAN NOT NULL DEFAULT FALSE,
    judge_verdict VARCHAR(20)
        CHECK (judge_verdict IS NULL OR judge_verdict IN
               ('A_wins','B_wins','hybrid_synthesis','escalate')),
    judge_rationale TEXT,
    transcript JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS reflections (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    cycle INTEGER NOT NULL,
    premortem_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    improvements JSONB NOT NULL DEFAULT '[]'::jsonb,
    v1_solution TEXT,
    v2_solution TEXT,
    improvement_delta DECIMAL(6,4) NOT NULL DEFAULT 0,
    converged BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS mcts_runs (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    simulations INTEGER NOT NULL DEFAULT 0,
    exploration_c DECIMAL(6,4) NOT NULL DEFAULT 1.4142,
    best_action JSONB,
    ucb1_scores JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS constitutional_checks (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    principle VARCHAR(10) NOT NULL
        CHECK (principle IN ('P1','P2','P3','P4','P5','P6','P7')),
    passed BOOLEAN NOT NULL,
    violation_reason TEXT,
    regeneration_constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_const_checks_principle
    ON constitutional_checks(principle, passed);

CREATE TABLE IF NOT EXISTS uncertainty_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    aleatory DECIMAL(6,4) NOT NULL DEFAULT 0,
    epistemic DECIMAL(6,4) NOT NULL DEFAULT 0,
    ontological DECIMAL(6,4) NOT NULL DEFAULT 0,
    computational DECIMAL(6,4) NOT NULL DEFAULT 0,
    credible_low DECIMAL(6,4) NOT NULL DEFAULT 0,
    credible_high DECIMAL(6,4) NOT NULL DEFAULT 1,
    propagation JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS bias_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    biases_detected JSONB NOT NULL DEFAULT '[]'::jsonb,
    mitigations_applied JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS meta_cognitive_reports (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    problem_class VARCHAR(30) NOT NULL,
    strategy_selected VARCHAR(60) NOT NULL,
    resources_allocated JSONB NOT NULL DEFAULT '{}'::jsonb,
    stuck_states_detected INTEGER NOT NULL DEFAULT 0,
    loops_detected INTEGER NOT NULL DEFAULT 0,
    stop_reason VARCHAR(40)
);

CREATE TABLE IF NOT EXISTS cognitive_decisions (
    decision_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    chosen JSONB NOT NULL,
    alternatives JSONB NOT NULL DEFAULT '[]'::jsonb,
    justification TEXT,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    risk_level VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (risk_level IN ('low','medium','high','critical')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cognitive_benchmarks (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    family VARCHAR(30) NOT NULL
        CHECK (family IN ('logic','mathematical','coding',
                           'reasoning_heavy','compliance')),
    score_0_100 DECIMAL(6,2) NOT NULL DEFAULT 0,
    baseline_delta DECIMAL(6,2),
    n_samples INTEGER NOT NULL DEFAULT 0,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Cache semantique des reasoning (pgvector ready, mais fallback sans)
CREATE TABLE IF NOT EXISTS reasoning_cache (
    cache_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    problem_hash CHAR(64) NOT NULL UNIQUE,
    problem_statement TEXT NOT NULL,
    final_answer JSONB,
    confidence DECIMAL(6,4) NOT NULL DEFAULT 0,
    original_trace_id UUID REFERENCES reasoning_traces(trace_id)
        ON DELETE SET NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);

-- Dependency graph : trace parent → traces derivees
CREATE TABLE IF NOT EXISTS reasoning_dependencies (
    id BIGSERIAL PRIMARY KEY,
    parent_trace UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    child_trace UUID REFERENCES reasoning_traces(trace_id) ON DELETE CASCADE,
    dependency_type VARCHAR(30) NOT NULL DEFAULT 'derives',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Circuit breaker kill events
CREATE TABLE IF NOT EXISTS cognitive_kill_events (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    reason VARCHAR(40) NOT NULL
        CHECK (reason IN ('timeout_5min','tokens_100k','iterations_50',
                           'memory_2gb','infinite_loop','stuck_state')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Human reasoning overrides
CREATE TABLE IF NOT EXISTS cognitive_human_overrides (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES reasoning_traces(trace_id) ON DELETE SET NULL,
    human_id VARCHAR(120) NOT NULL,
    new_decision JSONB NOT NULL,
    justification TEXT NOT NULL CHECK (length(justification) >= 50),
    impact_level VARCHAR(20) NOT NULL DEFAULT 'medium',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Adversarial test results
CREATE TABLE IF NOT EXISTS cognitive_adversarial_tests (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    scenario VARCHAR(120) NOT NULL,
    expected_behavior VARCHAR(60) NOT NULL,   -- "declare_unknown","escalate","conflict_signaled"
    actual_behavior VARCHAR(60) NOT NULL,
    passed BOOLEAN NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Reproducibility test results
CREATE TABLE IF NOT EXISTS cognitive_reproducibility_runs (
    id BIGSERIAL PRIMARY KEY,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    traces_replayed INTEGER NOT NULL DEFAULT 0,
    identical INTEGER NOT NULL DEFAULT 0,
    drifted INTEGER NOT NULL DEFAULT 0,
    drift_details JSONB NOT NULL DEFAULT '[]'::jsonb
);
-- ============================================================
-- 020_ctc_source_registry.sql - V5.3 BLOC 1
-- Registre versionne des sources de verite
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_sources (
    source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain VARCHAR(60) NOT NULL,        -- web_standards|security|compliance_dz|...
    url TEXT NOT NULL UNIQUE,
    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN ('api','documentation','specification',
                                'database','government','academic')),
    authority_tier INTEGER NOT NULL
        CHECK (authority_tier BETWEEN 1 AND 5),
    access_mode VARCHAR(40) NOT NULL
        CHECK (access_mode IN ('api_native','sdk_official','cli_official',
                                'connector_orchestrator','agentic_navigation',
                                'desktop_automation','manual')),
    freshness_policy_seconds INTEGER NOT NULL DEFAULT 86400,
    refresh_frequency VARCHAR(20) NOT NULL DEFAULT 'daily',
    checksum CHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','quarantined','deprecated')),
    last_validated_at TIMESTAMPTZ,
    access_justification TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_truth_sources_domain
    ON truth_sources(domain, authority_tier);
CREATE INDEX IF NOT EXISTS idx_truth_sources_status
    ON truth_sources(status);

-- Log fetch/harvest cycles
CREATE TABLE IF NOT EXISTS evidence_harvesting_log (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE CASCADE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    http_status INTEGER,
    bytes_received INTEGER NOT NULL DEFAULT 0,
    content_hash CHAR(64),
    changed BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_harvest_log_source
    ON evidence_harvesting_log(source_id, fetched_at DESC);

-- Circuit breaker events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL
        CHECK (event_type IN ('opened','half_open','closed','quarantined','restored')),
    reason TEXT,
    failures_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed quelques sources Tier 1-2 mondiales
INSERT INTO truth_sources(domain, url, source_type, authority_tier,
    access_mode, freshness_policy_seconds, refresh_frequency, notes)
VALUES
  ('web_standards', 'https://developer.mozilla.org/en-US/docs/Web',
    'documentation', 3, 'agentic_navigation', 86400, 'daily',
    'MDN Tier 3 (agregateur repute)'),
  ('web_standards', 'https://www.w3.org/standards/',
    'specification', 1, 'agentic_navigation', 604800, 'weekly',
    'W3C Tier 1 (standards)'),
  ('security', 'https://cve.mitre.org/',
    'database', 1, 'api_native', 900, '15min',
    'CVE MITRE Tier 1'),
  ('security', 'https://nvd.nist.gov/',
    'database', 1, 'api_native', 900, '15min',
    'NVD NIST Tier 1'),
  ('security', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
    'government', 1, 'api_native', 900, '15min',
    'CISA KEV Tier 1'),
  ('security', 'https://osv.dev/',
    'database', 2, 'api_native', 900, '15min',
    'OSV Tier 2 (Google)'),
  ('security', 'https://owasp.org/',
    'documentation', 1, 'agentic_navigation', 86400, 'daily',
    'OWASP Tier 1'),
  ('lang_python', 'https://docs.python.org/3/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'Python.org docs Tier 2'),
  ('framework', 'https://fastapi.tiangolo.com/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'FastAPI docs Tier 2'),
  ('database', 'https://www.postgresql.org/docs/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'PostgreSQL docs Tier 2'),
  ('compliance_dz', 'https://www.joradp.dz/',
    'government', 1, 'manual', 604800, 'weekly',
    'Journal Officiel DZ Tier 1'),
  ('compliance_eu', 'https://eur-lex.europa.eu/',
    'government', 1, 'agentic_navigation', 604800, 'weekly',
    'EUR-Lex Tier 1')
ON CONFLICT (url) DO NOTHING;
-- ============================================================
-- 021_ctc_assertions.sql - V5.3 BLOC 3
-- truth_assertions : assertions atomiques typees
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_assertions (
    assertion_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE SET NULL,
    source_version VARCHAR(80),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash CHAR(64) NOT NULL,
    normalized_text TEXT NOT NULL,
    assertion_type VARCHAR(20) NOT NULL
        CHECK (assertion_type IN (
            'fact','rule','constraint','warning','vulnerability',
            'deprecation','assumption','contradiction','benchmark','requirement')),
    domain VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('info','low','medium','high','critical')),
    confidence INTEGER NOT NULL DEFAULT 80
        CHECK (confidence BETWEEN 0 AND 100),
    freshness_score INTEGER NOT NULL DEFAULT 100
        CHECK (freshness_score BETWEEN 0 AND 100),
    status VARCHAR(20) NOT NULL DEFAULT 'unproven'
        CHECK (status IN ('proven','probable','unproven','conflicting','stale','blocked'))
);
CREATE INDEX IF NOT EXISTS idx_assertions_domain
    ON truth_assertions(domain, status);
CREATE INDEX IF NOT EXISTS idx_assertions_hash
    ON truth_assertions(content_hash);
CREATE INDEX IF NOT EXISTS idx_assertions_severity
    ON truth_assertions(severity, confidence DESC);

-- Conflits detectes entre sources
CREATE TABLE IF NOT EXISTS truth_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assertion_a UUID REFERENCES truth_assertions(assertion_id),
    assertion_b UUID REFERENCES truth_assertions(assertion_id),
    conflict_kind VARCHAR(30) NOT NULL
        CHECK (conflict_kind IN ('version_mismatch','scope_difference',
                                  'interpretation_difference','error','unknown')),
    resolution VARCHAR(30),
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
-- ============================================================
-- 022_ctc_truth_graph.sql - V5.3 BLOC 4
-- truth_assertion_links : graphe assertions ↔ artefacts ↔ decisions
-- WORM logique : append-only via triggers
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_assertion_links (
    link_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assertion_id UUID REFERENCES truth_assertions(assertion_id)
        ON DELETE CASCADE,
    linked_entity_type VARCHAR(30) NOT NULL
        CHECK (linked_entity_type IN
               ('task','artifact','validation','decision',
                'version','incident','hypothesis','risk')),
    linked_entity_id UUID NOT NULL,
    link_type VARCHAR(20) NOT NULL
        CHECK (link_type IN ('supports','contradicts','depends_on','invalidates')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tal_assertion
    ON truth_assertion_links(assertion_id);
CREATE INDEX IF NOT EXISTS idx_tal_entity
    ON truth_assertion_links(linked_entity_type, linked_entity_id);

-- Trigger append-only (WORM)
CREATE OR REPLACE FUNCTION truth_graph_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'truth_assertion_links is append-only (WORM)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tal_block_update ON truth_assertion_links;
CREATE TRIGGER trg_tal_block_update
    BEFORE UPDATE ON truth_assertion_links
    FOR EACH ROW EXECUTE FUNCTION truth_graph_block_mutations();

DROP TRIGGER IF EXISTS trg_tal_block_delete ON truth_assertion_links;
CREATE TRIGGER trg_tal_block_delete
    BEFORE DELETE ON truth_assertion_links
    FOR EACH ROW EXECUTE FUNCTION truth_graph_block_mutations();
-- ============================================================
-- 023_ctc_evidence_chain.sql - V5.3 BLOC 9
-- Chaine preuve cryptographique immuable HMAC-SHA256
-- ============================================================

CREATE TABLE IF NOT EXISTS evidence_chain_events (
    event_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    phase_id UUID,
    actor_type VARCHAR(20) NOT NULL
        CHECK (actor_type IN ('agent','validator','human','system')),
    actor_id VARCHAR(120) NOT NULL,
    ts_us BIGINT NOT NULL,           -- epoch microseconds
    input_hash CHAR(64) NOT NULL,
    output_hash CHAR(64) NOT NULL,
    artifact_hash CHAR(64),
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_event_hash CHAR(64) NOT NULL,
    chain_hash CHAR(64) NOT NULL UNIQUE,
    signature CHAR(64) NOT NULL,      -- HMAC-SHA256
    signing_key_id VARCHAR(40) NOT NULL,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('PASS','CONDITIONAL_PASS','SOFT_FAIL','HARD_FAIL',
                           'GENESIS','CHAIN_CHECK')),
    justification TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evchain_task
    ON evidence_chain_events(task_id, ts_us);
CREATE INDEX IF NOT EXISTS idx_evchain_created
    ON evidence_chain_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_evchain_actor
    ON evidence_chain_events(actor_type, actor_id);

-- Trigger append-only strict
CREATE OR REPLACE FUNCTION evidence_chain_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evidence_chain_events is IMMUTABLE (no UPDATE/DELETE)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evchain_block_update ON evidence_chain_events;
CREATE TRIGGER trg_evchain_block_update
    BEFORE UPDATE ON evidence_chain_events
    FOR EACH ROW EXECUTE FUNCTION evidence_chain_block_mutations();

DROP TRIGGER IF EXISTS trg_evchain_block_delete ON evidence_chain_events;
CREATE TRIGGER trg_evchain_block_delete
    BEFORE DELETE ON evidence_chain_events
    FOR EACH ROW EXECUTE FUNCTION evidence_chain_block_mutations();

-- Integrity checks log
CREATE TABLE IF NOT EXISTS evidence_chain_integrity_log (
    id BIGSERIAL PRIMARY KEY,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    events_checked INTEGER NOT NULL DEFAULT 0,
    broken_links INTEGER NOT NULL DEFAULT 0,
    bad_signatures INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(30) NOT NULL
        CHECK (status IN ('preserved','broken','quarantined')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- HMAC keys registry (metadata only ; cles reelles dans Vault)
CREATE TABLE IF NOT EXISTS evidence_signing_keys (
    key_id VARCHAR(40) PRIMARY KEY,
    vault_path VARCHAR(200) NOT NULL,
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at TIMESTAMPTZ,
    algorithm VARCHAR(20) NOT NULL DEFAULT 'HMAC-SHA256'
);
INSERT INTO evidence_signing_keys(key_id, vault_path, activated_at)
VALUES ('ctc-key-2026Q2', 'secret/uba/ctc/hmac_key_2026Q2', NOW())
ON CONFLICT (key_id) DO NOTHING;
-- ============================================================
-- 024_ctc_phase_gates.sql - V5.3 BLOC 11
-- 5 gates nommes + journal des tentatives de passage
-- ============================================================

CREATE TABLE IF NOT EXISTS phase_gates (
    gate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    phase_from VARCHAR(30) NOT NULL,
    phase_to VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','open','closed','rework')),
    validation_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_chain_ref UUID REFERENCES evidence_chain_events(event_id),
    actor VARCHAR(120) NOT NULL,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_phase_gates_task
    ON phase_gates(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase_gates_status
    ON phase_gates(status, created_at DESC);

-- Journal des echecs de passage (append-only)
CREATE TABLE IF NOT EXISTS phase_gate_failures (
    id BIGSERIAL PRIMARY KEY,
    gate_id UUID REFERENCES phase_gates(gate_id) ON DELETE CASCADE,
    reason_code VARCHAR(40) NOT NULL,
    reason_text TEXT NOT NULL,
    layers_failed JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Definition des 5 gates (statique pour introspection)
CREATE TABLE IF NOT EXISTS phase_gate_definitions (
    name VARCHAR(40) PRIMARY KEY,
    phase_from VARCHAR(30) NOT NULL,
    phase_to VARCHAR(30) NOT NULL,
    conditions JSONB NOT NULL,
    description TEXT
);

INSERT INTO phase_gate_definitions(name, phase_from, phase_to, conditions, description)
VALUES
  ('design_to_build', 'design', 'build',
   '{"rules":["no_open_ambiguity","specs_validated","requirements_proven"]}'::jsonb,
   'Toute ambiguite critique ouverte doit etre tracee'),
  ('build_to_validate', 'build', 'validate',
   '{"rules":["evidence_chain_bound","unit_tests_pass","sbom_generated"]}'::jsonb,
   'Artefacts lies a chaine evidence, tests unitaires OK'),
  ('validate_to_release', 'validate', 'release',
   '{"rules":["no_critical_contradictions","sources_fresh","7_layers_pass","all_dims_above_threshold"]}'::jsonb,
   '7 couches PASS + toutes dimensions >= seuil'),
  ('release_to_operate', 'release', 'operate',
   '{"rules":["security_proven","compliance_proven","prod_readiness_proven","chain_integrity"]}'::jsonb,
   'Securite + conformite + prod-readiness prouvees'),
  ('operate_to_rework', 'operate', 'rework',
   '{"rules":["anomaly_detected","evidence_stale","external_change","drift_detected"]}'::jsonb,
   'Anomalie/drift/changement externe declenchent rework')
ON CONFLICT (name) DO NOTHING;
-- ============================================================
-- 025_ctc_human_overrides.sql - V5.3 BLOC 17
-- Human overrides traceables + snapshots + backward compatibility
-- ============================================================

CREATE TABLE IF NOT EXISTS human_overrides (
    override_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    original_verdict_id UUID,
    new_verdict VARCHAR(30) NOT NULL,
    justification TEXT NOT NULL,
    human_id VARCHAR(120) NOT NULL,
    evidence_chain_event_id UUID REFERENCES evidence_chain_events(event_id),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','re_evaluated','expired','revoked')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    re_evaluated_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_overrides_status
    ON human_overrides(status, created_at DESC);

-- State snapshots (metadata - binary dump offline)
CREATE TABLE IF NOT EXISTS truth_engine_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tables_included JSONB NOT NULL,
    storage_path VARCHAR(500),
    compressed_bytes BIGINT,
    chain_integrity_ok BOOLEAN NOT NULL DEFAULT TRUE,
    retention_until TIMESTAMPTZ NOT NULL
        DEFAULT (NOW() + INTERVAL '90 days'),
    checksum CHAR(64)
);

-- Backward compatibility replay runs
CREATE TABLE IF NOT EXISTS truth_backward_replay (
    id BIGSERIAL PRIMARY KEY,
    version_old VARCHAR(40) NOT NULL,
    version_new VARCHAR(40) NOT NULL,
    verdicts_replayed INTEGER NOT NULL DEFAULT 0,
    identical INTEGER NOT NULL DEFAULT 0,
    improved INTEGER NOT NULL DEFAULT 0,
    regressed INTEGER NOT NULL DEFAULT 0,
    regression_details JSONB NOT NULL DEFAULT '[]'::jsonb,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verdict_pass BOOLEAN NOT NULL DEFAULT FALSE
);

-- Meta Truth Audit weekly results
CREATE TABLE IF NOT EXISTS meta_truth_audits (
    id BIGSERIAL PRIMARY KEY,
    audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    truth_tests_pass BOOLEAN NOT NULL DEFAULT FALSE,
    chain_integrity_ok BOOLEAN NOT NULL DEFAULT FALSE,
    sources_consulted INTEGER NOT NULL DEFAULT 0,
    rework_convergence_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    false_positive_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    false_negative_rate DECIMAL(6,4) NOT NULL DEFAULT 0,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('OK','REGRESSION','CRITICAL')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Budget + latency tracking
CREATE TABLE IF NOT EXISTS truth_budget_usage (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    layer VARCHAR(40) NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    cost_usd DECIMAL(10,6) NOT NULL DEFAULT 0,
    degraded_mode BOOLEAN NOT NULL DEFAULT FALSE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Chaos test results for CTC
CREATE TABLE IF NOT EXISTS truth_chaos_runs (
    id BIGSERIAL PRIMARY KEY,
    scenario VARCHAR(80) NOT NULL,
    ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_seconds INTEGER NOT NULL DEFAULT 0,
    ctc_continued_validation BOOLEAN NOT NULL DEFAULT FALSE,
    fallback_executed BOOLEAN NOT NULL DEFAULT FALSE,
    chain_integrity_preserved BOOLEAN NOT NULL DEFAULT FALSE,
    alerts_triggered INTEGER NOT NULL DEFAULT 0,
    recovery_time_seconds INTEGER NOT NULL DEFAULT 0,
    verdict VARCHAR(20) NOT NULL
        CHECK (verdict IN ('PASS','FAIL','DEGRADED'))
);
-- ============================================================
-- 026_automation_workflows.sql - V5.5 ETAPE 4.5
-- Tables pour workflows arq : executions, metrics, schedules, triggers
-- ============================================================

CREATE TABLE IF NOT EXISTS workflow_executions (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_name VARCHAR(120) NOT NULL,
    worker_name VARCHAR(120),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','succeeded','failed','timeout','dead_letter')),
    tries INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    trigger_kind VARCHAR(20) NOT NULL DEFAULT 'cron'
        CHECK (trigger_kind IN ('cron','event','manual'))
);
CREATE INDEX IF NOT EXISTS idx_wf_exec_task_started
    ON workflow_executions(task_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_wf_exec_status
    ON workflow_executions(status, started_at DESC);

CREATE TABLE IF NOT EXISTS workflow_metrics (
    id BIGSERIAL PRIMARY KEY,
    task_name VARCHAR(120) NOT NULL,
    day DATE NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms DECIMAL(12,2) NOT NULL DEFAULT 0,
    p99_duration_ms INTEGER NOT NULL DEFAULT 0,
    last_run TIMESTAMPTZ,
    UNIQUE (task_name, day)
);
CREATE INDEX IF NOT EXISTS idx_wf_metrics_task
    ON workflow_metrics(task_name, day DESC);

CREATE TABLE IF NOT EXISTS workflow_schedules (
    task_name VARCHAR(120) PRIMARY KEY,
    cron_expression VARCHAR(80) NOT NULL,
    tier INTEGER NOT NULL DEFAULT 3
        CHECK (tier BETWEEN 1 AND 7),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    paused_at TIMESTAMPTZ,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    description TEXT
);

CREATE TABLE IF NOT EXISTS event_triggers (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    task_name VARCHAR(120) NOT NULL,
    condition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_event_triggers_event
    ON event_triggers(event_type, enabled);

-- Dead letter queue
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id BIGSERIAL PRIMARY KEY,
    task_name VARCHAR(120) NOT NULL,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT,
    tries INTEGER NOT NULL DEFAULT 3,
    entered_dlq_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_dlq_resolved
    ON dead_letter_queue(resolved, entered_dlq_at DESC);

-- Seed workflow_schedules avec les 26 tasks
INSERT INTO workflow_schedules(task_name, cron_expression, tier, description)
VALUES
  ('task_queue_saturation_monitor', 'every 15m',  1, 'Monitor arq queue saturation'),
  ('task_health_deep_check',        'every 10m',  1, 'Deep health check services'),
  ('task_truth_integrity_check',    'every 30m',  1, 'Verify evidence chain integrity'),
  ('task_evidence_chain_verification','every 30m',1, 'Chain hash + HMAC audit'),
  ('task_vault_rotation_check',     '8/14/20 UTC',2, 'Vault key rotation audit'),
  ('task_tenant_isolation_audit',   '9/17 UTC',   2, 'RLS cross-tenant leaks check'),
  ('task_security_scan',            '06:00 daily',2, 'Bandit+secrets scan'),
  ('task_cve_poll',                 '0/6/12/18',  2, 'Poll CVE/NVD/KEV'),
  ('task_sbom_regeneration',        '02:30 daily',2, 'Regen SBOM + sign'),
  ('task_dependencies_audit',       '03:00 daily',2, 'Pip audit + advisory'),
  ('task_nightly_optimizer',        '01:00 daily',3, 'Nightly threshold tune'),
  ('task_meta_optimizer',           '02:00 daily',3, 'Capture meta metrics'),
  ('task_innovation_scout',         '03:30 daily',3, 'Scan innovation pipeline'),
  ('task_autonomy_chaos',           '02:30 daily',3, 'Run chaos scenarios'),
  ('task_drift_detection',          '04:00 daily',3, 'Detect performance/quality drift'),
  ('task_failure_archetype_mining', '04:30 daily',3, 'Cluster failures'),
  ('task_rework_convergence_audit', '05:00 daily',3, 'Audit rework cycles'),
  ('task_memory_consolidation',     '03:00 daily',4, 'Dedupe + prune memory'),
  ('task_prompt_variants_rebalance','04:00 daily',4, 'AB rebalance prompts'),
  ('task_benchmarks_run',           '05:30 daily',4, 'Run 5 families benchmarks'),
  ('task_cost_report_generation',   '07:00 daily',5, 'Daily cost report'),
  ('task_agent_performance_report', '07:30 daily',5, 'Per-agent perf report'),
  ('task_coverage_report',          '08:00 daily',5, 'Test coverage report'),
  ('task_regulatory_dz_poll',       '9/15 UTC',   6, 'Poll DZ regulations'),
  ('task_browser_contract_verify',  '06:30 daily',6, 'Browser contract'),
  ('task_backup_database',          '00:30/12:30',7, 'pg_dump + upload')
ON CONFLICT (task_name) DO UPDATE SET
  cron_expression = EXCLUDED.cron_expression,
  tier = EXCLUDED.tier,
  description = EXCLUDED.description;

-- Seed event triggers
INSERT INTO event_triggers(event_type, task_name)
VALUES
  ('git_commit', 'task_run_tests_impacted'),
  ('git_commit', 'task_lint_check'),
  ('git_commit', 'task_security_diff_scan'),
  ('migration_applied', 'task_schema_verify'),
  ('migration_applied', 'task_invariants_check'),
  ('migration_applied', 'task_regression_full'),
  ('new_project_created', 'task_auth_prefetcher'),
  ('new_project_created', 'task_risk_classification'),
  ('new_project_created', 'task_workflow_planner'),
  ('test_failure', 'task_failure_analysis'),
  ('cost_budget_approaching', 'task_budget_optimization'),
  ('regulatory_change_detected', 'task_impact_analysis'),
  ('agent_drift_detected', 'task_agent_diagnosis'),
  ('phase_gate_requested', 'task_validate_7_layers'),
  ('ahmed_response_received', 'task_response_classifier')
ON CONFLICT DO NOTHING;
-- ============================================================
-- 027_feature_flags.sql - V5.6 Universalite
-- Feature flags production-grade (hierarchie user > tenant > % rollout > global)
-- ============================================================

CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name VARCHAR(120) PRIMARY KEY,
    description TEXT,
    enabled_globally BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_tenants UUID[] NOT NULL DEFAULT '{}'::uuid[],
    enabled_users UUID[] NOT NULL DEFAULT '{}'::uuid[],
    rollout_percent INTEGER NOT NULL DEFAULT 0
        CHECK (rollout_percent BETWEEN 0 AND 100),
    condition_cel TEXT,
    auto_disable_on_error BOOLEAN NOT NULL DEFAULT FALSE,
    error_threshold_percent INTEGER NOT NULL DEFAULT 10
        CHECK (error_threshold_percent BETWEEN 1 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(200)
);
CREATE INDEX IF NOT EXISTS idx_feature_flags_globally
    ON feature_flags(enabled_globally) WHERE enabled_globally = TRUE;

CREATE TABLE IF NOT EXISTS feature_flag_events (
    id BIGSERIAL PRIMARY KEY,
    flag_name VARCHAR(120) NOT NULL,
    event_type VARCHAR(40) NOT NULL
        CHECK (event_type IN ('evaluated','error','toggle','rollout_changed')),
    tenant_id UUID,
    user_id UUID,
    result BOOLEAN,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ff_events_flag
    ON feature_flag_events(flag_name, created_at DESC);

-- Seed 5 flags de demo (1 par domaine)
INSERT INTO feature_flags(flag_name, description, enabled_globally)
VALUES
  ('domain.fiscal_dz.enabled',    'Active le domaine fiscal DZ',    TRUE),
  ('domain.juridique.enabled',    'Active le domaine juridique',    TRUE),
  ('domain.logistique.enabled',   'Active le domaine logistique',   TRUE),
  ('domain.rh.enabled',           'Active le domaine RH',           TRUE),
  ('domain.comptabilite.enabled', 'Active le domaine comptabilite', TRUE),
  ('feature.rules_hot_reload',    'Rechargement auto des rules YAML (<5s)', FALSE),
  ('feature.dark_mode',           'UI dark mode default',            TRUE)
ON CONFLICT (flag_name) DO NOTHING;
-- ============================================================
-- 028_slo_metrics.sql - V5.7 SLO/SLI tracking (fiabilite 99.8%)
-- ============================================================

CREATE TABLE IF NOT EXISTS slo_definitions (
    slo_name VARCHAR(80) PRIMARY KEY,
    description TEXT,
    target_percent DECIMAL(5,3) NOT NULL
        CHECK (target_percent > 0 AND target_percent < 100),
    window_days INTEGER NOT NULL DEFAULT 30,
    sli_type VARCHAR(40) NOT NULL
        CHECK (sli_type IN ('availability','latency','error_rate','freshness')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO slo_definitions(slo_name, description, target_percent, sli_type, window_days)
VALUES
  ('availability',       'Uptime global 30j',              99.800, 'availability', 30),
  ('latency_p99',        'Latence p99 HTTP < 500ms',       99.000, 'latency',      7),
  ('error_rate',         'Taux erreur 5xx < 0.2%',         99.800, 'error_rate',   7),
  ('backup_freshness',   'Dernier backup < 2h age',        99.500, 'freshness',   30)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS slo_measurements (
    id BIGSERIAL PRIMARY KEY,
    slo_name VARCHAR(80) NOT NULL REFERENCES slo_definitions(slo_name),
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    good_count BIGINT NOT NULL DEFAULT 0,
    bad_count BIGINT NOT NULL DEFAULT 0,
    total_count BIGINT GENERATED ALWAYS AS (good_count + bad_count) STORED,
    sli_value DECIMAL(8,5),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_slo_meas_name_ts
    ON slo_measurements(slo_name, measured_at DESC);

CREATE TABLE IF NOT EXISTS slo_incidents (
    id BIGSERIAL PRIMARY KEY,
    slo_name VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    severity VARCHAR(20) NOT NULL DEFAULT 'warning'
        CHECK (severity IN ('info','warning','critical')),
    burn_rate DECIMAL(6,2),
    reason TEXT,
    resolved_auto BOOLEAN NOT NULL DEFAULT FALSE,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_slo_incidents_slo
    ON slo_incidents(slo_name, started_at DESC);

-- Seed nouveau schedule V5.7 pour task_backup_hourly (backup incremental)
INSERT INTO workflow_schedules(task_name, cron_expression, tier, description)
VALUES
  ('task_backup_hourly', 'every hour at :15', 7, 'Backup incremental 24 derniers')
ON CONFLICT (task_name) DO UPDATE SET
  cron_expression = EXCLUDED.cron_expression,
  tier = EXCLUDED.tier,
  description = EXCLUDED.description;
-- ============================================================
-- 029_active_learning.sql - V5.8 Intelligence : active learning loop
-- ============================================================

CREATE TABLE IF NOT EXISTS active_learning_loops (
    id BIGSERIAL PRIMARY KEY,
    decision_id UUID,
    domain_id VARCHAR(80),
    input_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    original_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    original_confidence DECIMAL(5,3),
    proposals JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','accepted','rejected','modified','expired')),
    ahmed_choice JSONB,
    feedback_text TEXT,
    agreement_score DECIMAL(5,3),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days'
);
CREATE INDEX IF NOT EXISTS idx_active_learning_status
    ON active_learning_loops(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_active_learning_domain
    ON active_learning_loops(domain_id, created_at DESC);

CREATE TABLE IF NOT EXISTS active_learning_metrics (
    id BIGSERIAL PRIMARY KEY,
    window_days INTEGER NOT NULL DEFAULT 30,
    domain_id VARCHAR(80),
    total_loops INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    modified_count INTEGER NOT NULL DEFAULT 0,
    agreement_rate DECIMAL(5,3),
    improvement_delta DECIMAL(5,3),
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_al_metrics_computed
    ON active_learning_metrics(computed_at DESC);
-- ============================================================
-- 030_decisions_explanations.sql - V5.8 XAI (explainability)
-- ============================================================

CREATE TABLE IF NOT EXISTS decisions_explanations (
    decision_id UUID PRIMARY KEY,
    domain_id VARCHAR(80),
    operation VARCHAR(120),
    input_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    features_importance JSONB NOT NULL DEFAULT '[]'::jsonb,
    counterfactuals JSONB NOT NULL DEFAULT '[]'::jsonb,
    ahmed_summary TEXT,
    method VARCHAR(40) NOT NULL DEFAULT 'perturbation'
        CHECK (method IN ('perturbation','rules_trace','counterfactual',
                          'hybrid')),
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    computation_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_explanations_domain
    ON decisions_explanations(domain_id, generated_at DESC);
-- ============================================================
-- 031_knowledge_graph.sql - V5.8 Knowledge Graph (entites + relations)
-- ============================================================

CREATE TABLE IF NOT EXISTS kg_nodes (
    id VARCHAR(120) PRIMARY KEY,
    node_type VARCHAR(40) NOT NULL
        CHECK (node_type IN ('entity','rule','decision','evidence',
                              'domain','agent','feature_flag','task')),
    label TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kg_nodes_type
    ON kg_nodes(node_type);

CREATE TABLE IF NOT EXISTS kg_edges (
    id BIGSERIAL PRIMARY KEY,
    source_id VARCHAR(120) NOT NULL REFERENCES kg_nodes(id)
        ON DELETE CASCADE,
    target_id VARCHAR(120) NOT NULL REFERENCES kg_nodes(id)
        ON DELETE CASCADE,
    relation_type VARCHAR(40) NOT NULL
        CHECK (relation_type IN ('depends_on','contradicts','supports',
                                   'learned_from','derived_from','applies_to',
                                   'triggers','impacts')),
    weight DECIMAL(5,3) NOT NULL DEFAULT 1.0,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, target_id, relation_type)
);
CREATE INDEX IF NOT EXISTS idx_kg_edges_source
    ON kg_edges(source_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_target
    ON kg_edges(target_id, relation_type);
CREATE INDEX IF NOT EXISTS idx_kg_edges_contradicts
    ON kg_edges(relation_type)
    WHERE relation_type = 'contradicts';
-- 032 : V7 Production-Ready Local — chain seal + health thresholds env-overridable
-- 2026-04-25
-- Phase 7B repair :
--   * Anomalie A001 : truth_chain_integrity reportait 144 "broken" events.
--     Investigation : 0 chain_hash mismatch (cryptographie OK), 144 segment-boundaries
--     (resets legitimes hors-band — tests/chaos/redemarrages). verify_chain() est
--     desormais aligne sur le critere cryptographique (chain_hash recomputed) et
--     reporte les segments comme info, pas comme corruption.
--   * Anomalie A002/A003 : seuils health (PG=50ms, Redis=20ms) inadaptes a Docker
--     Desktop sur Windows. Desormais lus depuis ENV (PG_PING_HEALTHY_MS=200,
--     REDIS_PING_HEALTHY_MS=100). Code change : backend/app/health/checks.py.
--
-- Cette migration scelle la chaine au point V7 via un event "repair" qui
-- documente l'investigation et empeche regression silencieuse.

DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v7_chain_seal","version":"5.5.7","date":"2026-04-25","reason":"Phase 7B Anomalie A001 closure","investigation":{"chain_hash_mismatches":0,"segment_boundaries":144,"events_checked":3866},"resolution":"verify_chain aligned on cryptographic integrity (chain_hash recomputation), segment boundaries reported as info"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_032_v7',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V7 chain seal event inserted (chain_hash=%)', new_chain_hash;
END
$$;

-- Index pour stats segments (facultatif mais utile)
CREATE INDEX IF NOT EXISTS idx_evidence_kind_created
  ON evidence_ledger (kind, created_at DESC);
-- 033 : V8 OSINT Legal Framework
-- Tables : osint_consents, osint_audit_trail, osint_scope_whitelist
-- Triggers append-only sur audit_trail (pas d'UPDATE/DELETE).
-- 2026-04-26

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 1) osint_consents : contrats consentement explicite (pentest etc.)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_consents (
    consent_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    target               VARCHAR(255) NOT NULL,
    actions              JSONB        NOT NULL,
    contractor           VARCHAR(255) NOT NULL,
    contract_pdf_sha256  CHAR(64)     NOT NULL,
    signed_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    expires_at           TIMESTAMPTZ  NOT NULL,
    revoked_at           TIMESTAMPTZ,
    revoked_reason       TEXT,
    tenant_id            UUID,
    created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_osint_consents_target_active
  ON osint_consents (target)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_osint_consents_expires
  ON osint_consents (expires_at);

-- ---------------------------------------------------------------------------
-- 2) osint_audit_trail : append-only, hash-chained
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_audit_trail (
    id            BIGSERIAL    PRIMARY KEY,
    event_id      UUID         NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    actor         VARCHAR(120) NOT NULL,
    module        VARCHAR(120) NOT NULL,
    action        VARCHAR(120) NOT NULL,
    target        VARCHAR(255) NOT NULL,
    risk_level    VARCHAR(20)  NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    decision      VARCHAR(20)  NOT NULL CHECK (decision IN ('allowed','denied','error')),
    consent_id    UUID         REFERENCES osint_consents(consent_id) ON DELETE SET NULL,
    payload_hash  CHAR(64)     NOT NULL,
    prev_hash     CHAR(64)     NOT NULL,
    chain_hash    CHAR(64)     NOT NULL UNIQUE,
    payload_json  JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    tenant_id     UUID
);

CREATE INDEX IF NOT EXISTS idx_osint_audit_target ON osint_audit_trail (target);
CREATE INDEX IF NOT EXISTS idx_osint_audit_module_decision ON osint_audit_trail (module, decision);
CREATE INDEX IF NOT EXISTS idx_osint_audit_created_desc ON osint_audit_trail (created_at DESC);

-- Triggers : append-only stricte (refus UPDATE et DELETE)
CREATE OR REPLACE FUNCTION osint_audit_block_mutations()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'osint_audit_trail is append-only (V8 immuabilite RGPD-DZ)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_block_update ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_update
  BEFORE UPDATE ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_block_mutations();

DROP TRIGGER IF EXISTS trg_osint_audit_block_delete ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_delete
  BEFORE DELETE ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_block_mutations();

-- ---------------------------------------------------------------------------
-- 3) osint_scope_whitelist : entrees stricte d'extension whitelist
--    (rarement utilise — Dendani hardcoded dans le code Python pour empecher
--     un override SQL accidentel ; cette table garde un audit trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS osint_scope_whitelist (
    id            BIGSERIAL   PRIMARY KEY,
    scope_pattern VARCHAR(255) NOT NULL,
    reason        TEXT         NOT NULL,
    added_by      VARCHAR(120) NOT NULL,
    added_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    revoked_at    TIMESTAMPTZ,
    revoked_reason TEXT,
    tenant_id     UUID
);

CREATE INDEX IF NOT EXISTS idx_osint_whitelist_active
  ON osint_scope_whitelist (scope_pattern)
  WHERE revoked_at IS NULL;

-- ---------------------------------------------------------------------------
-- 4) Seal V8 : event marker dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v8_osint_legal_framework_init","version":"5.5.8","date":"2026-04-26","tables_created":["osint_consents","osint_audit_trail","osint_scope_whitelist"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_033_v8',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8 OSINT seal event inserted (chain_hash=%)', new_chain_hash;
END
$$;
-- 034 : V8.1 hotfix — audit_trail chain integrity
-- 2026-04-26
--
-- ROOT CAUSE :
--   Pendant la validation V8 phase 8F, un event de test a ete insere via SQL
--   brut pour verifier que le trigger UPDATE/DELETE bloque les mutations.
--   L'INSERT etait techniquement permis mais le chain_hash fourni etait
--   incorrect (sha256('h') au lieu de sha256(prev_hash || payload_hash)).
--   Resultat : verify_chain() detecte (correctement) une corruption.
--
-- FIX :
--   1. Disable temporairement les triggers UPDATE/DELETE.
--   2. Purger les events existants (1 row de test, pas de donnees production).
--   3. Re-enable triggers UPDATE/DELETE.
--   4. Ajouter trigger BEFORE INSERT qui valide que chain_hash =
--      sha256(prev_hash || payload_hash) — empeche TOUT futur insert raw SQL
--      avec hash invalide.
--   5. Ajouter trigger BEFORE TRUNCATE qui refuse TRUNCATE (sinon contournement
--      potentiel via TRUNCATE).

-- ---------------------------------------------------------------------------
-- 1) Disable triggers UPDATE/DELETE temporairement
-- ---------------------------------------------------------------------------
ALTER TABLE osint_audit_trail DISABLE TRIGGER trg_osint_audit_block_delete;
ALTER TABLE osint_audit_trail DISABLE TRIGGER trg_osint_audit_block_update;

-- 2) Purger les events de test V8F (chain corrompue)
DELETE FROM osint_audit_trail;

-- 3) Re-enable les triggers
ALTER TABLE osint_audit_trail ENABLE TRIGGER trg_osint_audit_block_delete;
ALTER TABLE osint_audit_trail ENABLE TRIGGER trg_osint_audit_block_update;

-- 4) Trigger BEFORE INSERT — validation cryptographique du chain_hash
CREATE OR REPLACE FUNCTION osint_audit_validate_insert()
RETURNS TRIGGER AS $$
DECLARE
    last_chain_hash TEXT;
    expected_chain  TEXT;
BEGIN
    -- prev_hash doit pointer sur le chain_hash du dernier event, OU genesis
    -- pour le tout premier insert.
    SELECT chain_hash INTO last_chain_hash
    FROM osint_audit_trail
    ORDER BY id DESC
    LIMIT 1;

    IF last_chain_hash IS NULL THEN
        -- Premier event : prev_hash doit etre genesis (64 zeros)
        IF NEW.prev_hash <> repeat('0', 64) THEN
            RAISE EXCEPTION 'osint_audit_trail: first event prev_hash must be genesis (64 zeros), got %', NEW.prev_hash;
        END IF;
    ELSE
        -- Suivants : prev_hash doit matcher dernier chain_hash
        IF NEW.prev_hash <> last_chain_hash THEN
            RAISE EXCEPTION 'osint_audit_trail: prev_hash mismatch (expected %, got %)', last_chain_hash, NEW.prev_hash;
        END IF;
    END IF;

    -- chain_hash doit etre sha256(prev_hash || payload_hash)
    expected_chain := encode(digest(NEW.prev_hash || NEW.payload_hash, 'sha256'), 'hex');
    IF NEW.chain_hash <> expected_chain THEN
        RAISE EXCEPTION 'osint_audit_trail: chain_hash invalid (expected %, got %)', expected_chain, NEW.chain_hash;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_validate_insert ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_validate_insert
  BEFORE INSERT ON osint_audit_trail
  FOR EACH ROW EXECUTE FUNCTION osint_audit_validate_insert();

-- 5) Trigger BEFORE TRUNCATE — bloque le TRUNCATE (sinon bypass des UPDATE/DELETE)
CREATE OR REPLACE FUNCTION osint_audit_block_truncate()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'osint_audit_trail: TRUNCATE refused (V8.1 immuabilite stricte)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_osint_audit_block_truncate ON osint_audit_trail;
CREATE TRIGGER trg_osint_audit_block_truncate
  BEFORE TRUNCATE ON osint_audit_trail
  FOR EACH STATEMENT EXECUTE FUNCTION osint_audit_block_truncate();

-- ---------------------------------------------------------------------------
-- 6) Seal V8.1 dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v8_1_audit_chain_integrity_fix","version":"5.5.8.1","date":"2026-04-26","fix":"INSERT validation trigger added; TRUNCATE blocked; legacy test event purged"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_034_v8_1',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.1 audit chain integrity fix sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 035 : V8.5 — delivery quality gates persistence
-- 2026-04-27
--
-- Persiste l'historique des 6 quality gates executees avant chaque livraison
-- d'un projet, pour audit + dashboard + auto-retry.
--
-- Tables :
--   delivery_quality_gates  : ligne par execution d'un gate
--   quality_gate_failures   : detail par echec (pour feedback aux agents)

-- ---------------------------------------------------------------------------
-- 1) delivery_quality_gates : historique brut des executions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS delivery_quality_gates (
    id              BIGSERIAL PRIMARY KEY,
    project_id      UUID NOT NULL,
    attempt_number  INTEGER NOT NULL DEFAULT 1,
    gate_name       TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PASS','FAIL','SKIP','ERROR')),
    score           NUMERIC(5,3),
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    details_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dqg_project_attempt
    ON delivery_quality_gates(project_id, attempt_number, gate_name);

CREATE INDEX IF NOT EXISTS idx_dqg_status_recent
    ON delivery_quality_gates(status, checked_at DESC);

CREATE INDEX IF NOT EXISTS idx_dqg_gate_name_recent
    ON delivery_quality_gates(gate_name, checked_at DESC);

-- ---------------------------------------------------------------------------
-- 2) quality_gate_failures : detail des echecs (pour feedback aux agents)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_gate_failures (
    id                BIGSERIAL PRIMARY KEY,
    project_id        UUID NOT NULL,
    gate_name         TEXT NOT NULL,
    attempt_number    INTEGER NOT NULL,
    error_msg         TEXT NOT NULL,
    fixed_in_attempt  INTEGER,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qgf_project_open
    ON quality_gate_failures(project_id, fixed_in_attempt) WHERE fixed_in_attempt IS NULL;

CREATE INDEX IF NOT EXISTS idx_qgf_gate_recent
    ON quality_gate_failures(gate_name, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3) Seal V8.5 dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v8_5_quality_gates_strict","version":"6.3.0","date":"2026-04-27","fix":"6 strict gates blocking delivery; pytest_agent fallback parser; templates include pytest-json-report"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_035_v8_5',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.5 quality gates strict sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 036 : V8.5 — validation score v2 (breakdown + attempts)
-- 2026-04-27
--
-- Ajoute aux tables `tasks` les colonnes pour persister le breakdown reel
-- du nouveau validation_score (echelle 0..100, 6 composantes), le nombre
-- de tentatives de re-generation, et l'historique des quality gates.

-- ---------------------------------------------------------------------------
-- 1) tasks : nouvelles colonnes
-- ---------------------------------------------------------------------------
ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS validation_breakdown_json JSONB,
    ADD COLUMN IF NOT EXISTS validation_attempts INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS quality_gates_history_json JSONB,
    ADD COLUMN IF NOT EXISTS validation_decision TEXT
        CHECK (validation_decision IN ('ACCEPTED','PARTIAL','REJECTED'));

-- Index pour requetes dashboard "tasks par decision"
CREATE INDEX IF NOT EXISTS idx_tasks_validation_decision
    ON tasks(validation_decision)
    WHERE validation_decision IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_validation_attempts_high
    ON tasks(validation_attempts DESC)
    WHERE validation_attempts >= 2;

-- ---------------------------------------------------------------------------
-- 2) Vue dashboard : score breakdown agrege
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_validation_breakdown_summary AS
SELECT
    validation_decision,
    COUNT(*) AS task_count,
    AVG((validation_breakdown_json->>'total')::int) AS avg_total,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (validation_breakdown_json->>'total')::int) AS p50_total,
    AVG(validation_attempts) AS avg_attempts,
    SUM(CASE WHEN validation_attempts >= 3 THEN 1 ELSE 0 END) AS exhausted_count
FROM tasks
WHERE validation_breakdown_json IS NOT NULL
GROUP BY validation_decision;

-- ---------------------------------------------------------------------------
-- 3) Seal V8.5D dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v8_5d_validation_score_v2","version":"6.3.0","date":"2026-04-27","fix":"100-pt breakdown ; tasks.validation_breakdown_json + validation_attempts + validation_decision"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_036_v8_5d',
        'repair',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V8.5D validation score v2 sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 037 : V9 Phase 9A — direct-link catalog (liens d'action a usage controle)
-- 2026-04-29
--
-- Tables :
--   direct_links        : liens emis (token_hash uniquement, jamais le brut)
--   direct_links_audit  : journal append-only (issued, viewed, consumed, ...)
--
-- Le token brut quitte le serveur dans l'URL et n'est jamais re-stocke.
-- Si la base fuit, les hashs ne permettent pas de retrouver les tokens.
--
-- Numerotation 037 : reservee pour Phase 9A dans le master plan V9.

-- ---------------------------------------------------------------------------
-- 1) direct_links : registre des liens actifs / passes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS direct_links (
    id                 BIGSERIAL PRIMARY KEY,
    link_id            UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    token_hash         TEXT NOT NULL UNIQUE,             -- sha256 du token urlsafe
    action_type        TEXT NOT NULL,                     -- valide via catalog.json (cote app)
    target_id          TEXT NOT NULL,                     -- id metier (handoff, project, deliverable)
    principal_id       TEXT,                              -- utilisateur autorise (optionnel)
    metadata_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    single_use         BOOLEAN NOT NULL DEFAULT FALSE,
    consumed_at        TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revocation_reason  TEXT,
    expires_at         TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_direct_links_action_target
    ON direct_links(action_type, target_id);

CREATE INDEX IF NOT EXISTS idx_direct_links_active_expiry
    ON direct_links(expires_at)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_direct_links_principal_recent
    ON direct_links(principal_id, created_at DESC)
    WHERE principal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_direct_links_action_type_recent
    ON direct_links(action_type, created_at DESC);

-- ---------------------------------------------------------------------------
-- 2) direct_links_audit : journal append-only (1 ligne par evenement)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS direct_links_audit (
    id            BIGSERIAL PRIMARY KEY,
    link_id       UUID,                                  -- nullable pour invalid_token
    event         TEXT NOT NULL CHECK (event IN
                      ('issued','viewed','consumed','expired',
                       'revoked','invalid_token','unknown')),
    user_agent    TEXT,
    ip_hash       TEXT,                                  -- sha256 de l'IP (RGPD)
    detail_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dla_link_recent
    ON direct_links_audit(link_id, occurred_at DESC)
    WHERE link_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_dla_event_recent
    ON direct_links_audit(event, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_dla_invalid_recent
    ON direct_links_audit(occurred_at DESC)
    WHERE event = 'invalid_token';

-- ---------------------------------------------------------------------------
-- 3) Seal V9 Phase 9A dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9a_direct_links","version":"9.0.0-phase9a","date":"2026-04-29","tables":["direct_links","direct_links_audit"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_037_v9_direct_links',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9A direct_links sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 038 : V9 Phase 9H — Billing + Stripe Checkout (1-shot)
-- 2026-04-30
--
-- 4 tables :
--   payments          : table CANONIQUE des paiements (UUID PK, FK depuis 9G/9F en 9P)
--   invoices          : factures emises (multi-pays, multi-langues)
--   refunds           : refunds partiels/complets
--   webhook_events    : journal Stripe avec idempotency_key UNIQUE

-- ---------------------------------------------------------------------------
-- 1) payments (canonique)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    id                          BIGSERIAL PRIMARY KEY,
    payment_id                  UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id                  TEXT NOT NULL,
    stripe_session_id           TEXT,
    stripe_payment_intent_id    TEXT,
    amount_cents                INTEGER NOT NULL CHECK (amount_cents >= 0),
    currency                    CHAR(3) NOT NULL,
    status                      TEXT NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','succeeded','failed',
                                                      'refunded','partially_refunded',
                                                      'cancelled')),
    owner_email                 TEXT NOT NULL,
    country                     CHAR(2) NOT NULL,
    locale                      TEXT NOT NULL DEFAULT 'en',
    metadata_json               JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at                     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_payments_project_recent
    ON payments(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_status_recent
    ON payments(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_payments_stripe_session
    ON payments(stripe_session_id)
    WHERE stripe_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_stripe_pi
    ON payments(stripe_payment_intent_id)
    WHERE stripe_payment_intent_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_pending
    ON payments(created_at DESC)
    WHERE status = 'pending';

-- ---------------------------------------------------------------------------
-- 2) invoices (multi-pays, multi-langues)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id                    BIGSERIAL PRIMARY KEY,
    invoice_id            UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    invoice_number        TEXT NOT NULL UNIQUE,            -- ex. UBA-202604-000001
    payment_id            UUID NOT NULL REFERENCES payments(payment_id),
    project_id            TEXT NOT NULL,
    owner_email           TEXT NOT NULL,
    country               CHAR(2) NOT NULL,
    locale                TEXT NOT NULL DEFAULT 'en',
    description           TEXT NOT NULL DEFAULT '',
    net_amount_cents      INTEGER NOT NULL CHECK (net_amount_cents >= 0),
    vat_pct               NUMERIC(5,2) NOT NULL DEFAULT 0,
    vat_amount_cents      INTEGER NOT NULL DEFAULT 0,
    gross_amount_cents    INTEGER NOT NULL CHECK (gross_amount_cents >= 0),
    currency              CHAR(3) NOT NULL,
    vat_label             TEXT NOT NULL DEFAULT 'VAT',
    pdf_url               TEXT,                            -- rempli par job async
    seq_in_month          INTEGER NOT NULL,
    issued_year           INTEGER NOT NULL,
    issued_month          INTEGER NOT NULL CHECK (issued_month BETWEEN 1 AND 12),
    issued_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (issued_year, issued_month, seq_in_month)
);

CREATE INDEX IF NOT EXISTS idx_invoices_project_recent
    ON invoices(project_id, issued_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_owner_recent
    ON invoices(owner_email, issued_at DESC);

CREATE INDEX IF NOT EXISTS idx_invoices_country_month
    ON invoices(country, issued_year, issued_month);

-- ---------------------------------------------------------------------------
-- 3) refunds
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS refunds (
    id                  BIGSERIAL PRIMARY KEY,
    refund_id           UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    payment_id          UUID NOT NULL REFERENCES payments(payment_id),
    amount_cents        INTEGER NOT NULL CHECK (amount_cents > 0),
    reason              TEXT NOT NULL CHECK (reason IN
                            ('sla_violation','duplicate_payment',
                             'requested_by_customer','fraudulent',
                             'project_cancelled','other')),
    detail              TEXT NOT NULL DEFAULT '',
    stripe_refund_id    TEXT,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_refunds_payment_recent
    ON refunds(payment_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_refunds_reason_recent
    ON refunds(reason, requested_at DESC);

-- ---------------------------------------------------------------------------
-- 4) webhook_events : Stripe + autres sources (idempotency strict)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS webhook_events (
    id                    BIGSERIAL PRIMARY KEY,
    event_db_id           UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    idempotency_key       TEXT NOT NULL UNIQUE,            -- e.g. event.id de Stripe
    source                TEXT NOT NULL DEFAULT 'stripe',
    event_type            TEXT NOT NULL,
    signature_verified    BOOLEAN NOT NULL DEFAULT FALSE,
    payload_json          JSONB NOT NULL,
    payment_id            UUID REFERENCES payments(payment_id),
    received_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_type_recent
    ON webhook_events(event_type, received_at DESC);

CREATE INDEX IF NOT EXISTS idx_webhook_events_unprocessed
    ON webhook_events(received_at DESC)
    WHERE processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_webhook_events_payment
    ON webhook_events(payment_id, received_at DESC)
    WHERE payment_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Vues : revenue 30j + funnel
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_revenue_30d AS
SELECT
    currency,
    COUNT(*) FILTER (WHERE status = 'succeeded') AS paid_count,
    SUM(amount_cents) FILTER (WHERE status = 'succeeded') AS total_paid_cents,
    SUM(amount_cents) FILTER (WHERE status = 'refunded') AS total_refunded_cents,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count
  FROM payments
 WHERE created_at >= NOW() - INTERVAL '30 days'
 GROUP BY currency;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9H
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9h_billing","version":"9.0.0-phase9h","date":"2026-04-30","tables":["payments","invoices","refunds","webhook_events"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_038_v9_billing',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9H billing sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 039 : V9 Phase 9G — Hostinger Provisioning
-- 2026-04-30
--
-- 5 tables :
--   hostinger_resources   : registre des ressources (domain, vps, ssl, backup)
--   hostinger_audit       : journal append-only des operations API
--   domain_searches       : historique des recherches (lecture libre)
--   ssl_certificates      : certificats Let's Encrypt
--   backups               : sauvegardes quotidiennes
--
-- Numero 039 : reserve dans le master plan V9 a Phase 9G.

-- ---------------------------------------------------------------------------
-- 1) hostinger_resources : etat de chaque ressource externe
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hostinger_resources (
    id              BIGSERIAL PRIMARY KEY,
    resource_id     UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    resource_type   TEXT NOT NULL CHECK (resource_type IN ('domain','vps','ssl','backup')),
    project_id      TEXT NOT NULL,
    hostinger_id    TEXT,                                  -- id chez Hostinger
    status          TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','provisioning','active',
                                          'failed','destroyed')),
    payment_id      TEXT,                                  -- ref vers billing (FK en 9P)
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hostres_project_recent
    ON hostinger_resources(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hostres_type_status
    ON hostinger_resources(resource_type, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hostres_hostinger_id
    ON hostinger_resources(hostinger_id)
    WHERE hostinger_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hostres_active_recent
    ON hostinger_resources(updated_at DESC)
    WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 2) hostinger_audit : journal append-only des operations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hostinger_audit (
    id              BIGSERIAL PRIMARY KEY,
    audit_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    resource_id     UUID,                                  -- nullable (audit pre-creation)
    event           TEXT NOT NULL,                         -- e.g. 'purchase_requested'
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hostaudit_resource_recent
    ON hostinger_audit(resource_id, occurred_at DESC)
    WHERE resource_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hostaudit_event_recent
    ON hostinger_audit(event, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- 3) domain_searches : historique des recherches (utile pour analytics)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS domain_searches (
    id            BIGSERIAL PRIMARY KEY,
    search_id     UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    query         TEXT NOT NULL,
    available     BOOLEAN NOT NULL,
    raw_json      JSONB NOT NULL DEFAULT '{}'::jsonb,
    searched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_domsearch_query_recent
    ON domain_searches(query, searched_at DESC);

-- ---------------------------------------------------------------------------
-- 4) ssl_certificates : Let's Encrypt
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ssl_certificates (
    id                       BIGSERIAL PRIMARY KEY,
    cert_id                  UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id               TEXT NOT NULL,
    domain                   TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'pending'
                                CHECK (status IN ('pending','issued','renewing',
                                                   'expired','failed')),
    issued_at                TIMESTAMPTZ,
    expires_at               TIMESTAMPTZ,
    last_renewed_at          TIMESTAMPTZ,
    hostinger_metadata_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_ssl_project_recent
    ON ssl_certificates(project_id, issued_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_ssl_expires_soon
    ON ssl_certificates(expires_at)
    WHERE status = 'issued' AND expires_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5) backups : sauvegardes quotidiennes
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS backups (
    id                    BIGSERIAL PRIMARY KEY,
    backup_id             UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id            TEXT NOT NULL,
    vps_resource_id       UUID NOT NULL REFERENCES hostinger_resources(resource_id),
    status                TEXT NOT NULL DEFAULT 'scheduled'
                             CHECK (status IN ('scheduled','running','completed',
                                                'failed','restoring','restored')),
    size_bytes            BIGINT,
    hostinger_backup_id   TEXT,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backups_project_recent
    ON backups(project_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_backups_vps
    ON backups(vps_resource_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_backups_status_recent
    ON backups(status, started_at DESC);

-- ---------------------------------------------------------------------------
-- Vues pratiques
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ssl_expires_30d AS
SELECT cert_id, project_id, domain, expires_at,
       (expires_at - NOW()) AS time_remaining
  FROM ssl_certificates
 WHERE status = 'issued'
   AND expires_at IS NOT NULL
   AND expires_at <= NOW() + INTERVAL '30 days'
 ORDER BY expires_at ASC;

CREATE OR REPLACE VIEW v_active_resources_per_project AS
SELECT project_id, resource_type, COUNT(*) AS count_active
  FROM hostinger_resources
 WHERE status = 'active'
 GROUP BY project_id, resource_type;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9G
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9g_hostinger_provisioning","version":"9.0.0-phase9g","date":"2026-04-30","tables":["hostinger_resources","hostinger_audit","domain_searches","ssl_certificates","backups"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_039_v9_hostinger',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9G hostinger_provisioning sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 040 : V9 Phase 9D — journalisation des decisions IA
-- 2026-04-30
--
-- 1 ligne par appel via `AIRouter.route()`. Sert :
-- - au CostGuard pour calculer la depense cumulee par projet et par jour
-- - au dashboard FinOps pour visualiser le cout reel par projet
-- - a l'analyse post-mortem (loops, fallbacks, erreurs)

CREATE TABLE IF NOT EXISTS ai_decisions_log (
    id                  BIGSERIAL PRIMARY KEY,
    decision_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    requested_provider  TEXT NOT NULL,
    actual_provider     TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                            ('ok','fallback','error',
                             'budget_blocked','loop_blocked')),
    prompt_hash         TEXT NOT NULL,                  -- sha256 du prompt
    prompt_preview      TEXT,                           -- 200 premiers chars (debug)
    response_preview    TEXT,                           -- 200 premiers chars (debug)
    tokens_in           INTEGER NOT NULL DEFAULT 0,
    tokens_out          INTEGER NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms          INTEGER NOT NULL DEFAULT 0,
    fallback_used       BOOLEAN NOT NULL DEFAULT FALSE,
    retries             INTEGER NOT NULL DEFAULT 0,
    loop_detected       BOOLEAN NOT NULL DEFAULT FALSE,
    error_msg           TEXT,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_dec_project_recent
    ON ai_decisions_log(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_status_recent
    ON ai_decisions_log(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_actual_provider_recent
    ON ai_decisions_log(actual_provider, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_cost_window
    ON ai_decisions_log(created_at DESC, cost_usd);

CREATE INDEX IF NOT EXISTS idx_ai_dec_loop_recent
    ON ai_decisions_log(created_at DESC)
    WHERE loop_detected = TRUE;

CREATE INDEX IF NOT EXISTS idx_ai_dec_blocked_recent
    ON ai_decisions_log(status, created_at DESC)
    WHERE status IN ('budget_blocked','loop_blocked');

-- ---------------------------------------------------------------------------
-- Vue dashboard : cout par projet / 24h
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ai_cost_24h AS
SELECT
    project_id,
    COUNT(*) AS calls,
    SUM(cost_usd)::NUMERIC(12,6) AS total_cost_usd,
    SUM(tokens_in)::BIGINT AS tokens_in,
    SUM(tokens_out)::BIGINT AS tokens_out,
    SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END)::INT AS fallbacks,
    SUM(CASE WHEN loop_detected THEN 1 ELSE 0 END)::INT AS loops,
    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END)::INT AS errors
FROM ai_decisions_log
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY project_id;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9D
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9d_ai_orchestrator","version":"9.0.0-phase9d","date":"2026-04-30","tables":["ai_decisions_log"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_040_v9_ai_orchestrator',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9D ai_orchestrator sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 041 : V9 Phase 9C — Intelligence Engine (qualifications + pricings + assemblies + progression)
-- 2026-04-30
--
-- Le master plan reservait 041 a 'pricing_history' uniquement, mais Phase 9C
-- englobe aussi qualifications/assemblies/progression. On consolide en une
-- seule migration coherente, voir ADR-11.
--
-- Tables :
--   intelligence_qualifications : 1 ligne par CDC analyse
--   intelligence_pricings       : 1 ligne par devis emis
--   intelligence_assemblies     : 1 ligne par assemblage qualification + pricing + pack
--   project_progression         : 6 lignes par projet (1 par phase)

-- ---------------------------------------------------------------------------
-- 1) intelligence_qualifications
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_qualifications (
    id                  BIGSERIAL PRIMARY KEY,
    qualification_id    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    pack_hint           TEXT NOT NULL,
    facets_json         JSONB NOT NULL,
    detected_domain     TEXT NOT NULL,
    detected_locales    TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    risks               TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    confidence          TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    rationale           TEXT NOT NULL,
    cdc_text_hash       TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_iq_project_recent
    ON intelligence_qualifications(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_iq_pack_hint
    ON intelligence_qualifications(pack_hint, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_iq_low_confidence
    ON intelligence_qualifications(created_at DESC)
    WHERE confidence = 'low';

CREATE INDEX IF NOT EXISTS idx_iq_cdc_hash
    ON intelligence_qualifications(cdc_text_hash);

-- ---------------------------------------------------------------------------
-- 2) intelligence_pricings (= "pricing_history" du master plan)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_pricings (
    id                BIGSERIAL PRIMARY KEY,
    pricing_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id        TEXT NOT NULL,
    pack_id           TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('ok','requires_manual_quote')),
    currency          TEXT NOT NULL,
    net_price         NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount        NUMERIC(12,2) NOT NULL DEFAULT 0,
    gross_price       NUMERIC(12,2) NOT NULL DEFAULT 0,
    facets_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    coefficients_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    breakdown_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ip_project_recent
    ON intelligence_pricings(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ip_status
    ON intelligence_pricings(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ip_pack
    ON intelligence_pricings(pack_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3) intelligence_assemblies
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_assemblies (
    id                  BIGSERIAL PRIMARY KEY,
    assembly_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    qualification_id    UUID NOT NULL REFERENCES intelligence_qualifications(qualification_id),
    pricing_id          UUID REFERENCES intelligence_pricings(pricing_id),
    pack_id             TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('auto','manual_quote','degraded')),
    modules             TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    deliverables        TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    selected_addons     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    phase_weights_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ia_project_recent
    ON intelligence_assemblies(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ia_outcome
    ON intelligence_assemblies(outcome, created_at DESC);

-- ---------------------------------------------------------------------------
-- 4) project_progression : 6 lignes par projet (1 par phase)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_progression (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            TEXT NOT NULL,
    phase                 TEXT NOT NULL CHECK (phase IN
                              ('ANALYSIS','DESIGN','CORE','FEATURES','TESTING','DEPLOY')),
    weight_pct            INTEGER NOT NULL CHECK (weight_pct BETWEEN 1 AND 60),
    status                TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','in_progress','done')),
    completion_pct        INTEGER NOT NULL DEFAULT 0
                              CHECK (completion_pct BETWEEN 0 AND 100),
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    paywall_triggered_at  TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, phase)
);

CREATE INDEX IF NOT EXISTS idx_pp_project_phase
    ON project_progression(project_id, phase);

CREATE INDEX IF NOT EXISTS idx_pp_in_progress
    ON project_progression(updated_at DESC)
    WHERE status = 'in_progress';

CREATE INDEX IF NOT EXISTS idx_pp_paywall
    ON project_progression(paywall_triggered_at DESC)
    WHERE paywall_triggered_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5) Seal V9 Phase 9C dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9c_intelligence_engine","version":"9.0.0-phase9c","date":"2026-04-30","tables":["intelligence_qualifications","intelligence_pricings","intelligence_assemblies","project_progression"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_041_v9_intelligence',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9C intelligence engine sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 042 : V9 Phase 9J — Audit trail immutability triggers (append-only)
-- 2026-04-30
--
-- Bloque UPDATE/DELETE sur les tables append-only :
--   - admin_actions       (Phase 9N)
--   - ai_decisions_log    (Phase 9D)
--   - hostinger_audit     (Phase 9G)
--   - direct_links_audit  (Phase 9A)
--   - webhook_events      (Phase 9H — payload_json/signature_verified
--                          immuables ; processed_at/payment_id peuvent
--                          etre completes 1 fois)
--
-- Pour `mandates` (Phase 9-BOOT) : trigger column-level — chain_hash,
-- prev_hash, payload_hash, signed_at sont immuables ; revoked_at,
-- revocation_reason et audit_log peuvent etre mis a jour (revocation
-- legitime). signature integrite preservee.

-- ---------------------------------------------------------------------------
-- 1) Helper : RAISE EXCEPTION trigger function pour append-only strict
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_block_mutations() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'append-only: % on % bloque par audit trail',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- 2) Triggers stricts sur tables 100% append-only
-- ---------------------------------------------------------------------------
-- admin_actions : aucune mutation
DROP TRIGGER IF EXISTS trg_admin_actions_no_update ON admin_actions;
CREATE TRIGGER trg_admin_actions_no_update
    BEFORE UPDATE OR DELETE ON admin_actions
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- ai_decisions_log : aucune mutation
DROP TRIGGER IF EXISTS trg_ai_decisions_log_no_update ON ai_decisions_log;
CREATE TRIGGER trg_ai_decisions_log_no_update
    BEFORE UPDATE OR DELETE ON ai_decisions_log
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- hostinger_audit : aucune mutation
DROP TRIGGER IF EXISTS trg_hostinger_audit_no_update ON hostinger_audit;
CREATE TRIGGER trg_hostinger_audit_no_update
    BEFORE UPDATE OR DELETE ON hostinger_audit
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();

-- direct_links_audit : aucune mutation
DROP TRIGGER IF EXISTS trg_direct_links_audit_no_update ON direct_links_audit;
CREATE TRIGGER trg_direct_links_audit_no_update
    BEFORE UPDATE OR DELETE ON direct_links_audit
    FOR EACH ROW EXECUTE FUNCTION fn_block_mutations();


-- ---------------------------------------------------------------------------
-- 3) webhook_events : payload_json/signature_verified/event_type immuables ;
--    processed_at + payment_id peuvent etre completes 1 fois
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_webhook_events_protect() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'webhook_events: DELETE bloque (immuable)'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- UPDATE : on protege les champs immuables
    IF NEW.idempotency_key  IS DISTINCT FROM OLD.idempotency_key
       OR NEW.payload_json    IS DISTINCT FROM OLD.payload_json
       OR NEW.signature_verified IS DISTINCT FROM OLD.signature_verified
       OR NEW.event_type      IS DISTINCT FROM OLD.event_type
       OR NEW.source          IS DISTINCT FROM OLD.source
       OR NEW.received_at     IS DISTINCT FROM OLD.received_at
    THEN
        RAISE EXCEPTION 'webhook_events: champs immuables modifies'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- processed_at peut etre rempli mais pas reverte
    IF OLD.processed_at IS NOT NULL
       AND NEW.processed_at IS DISTINCT FROM OLD.processed_at
    THEN
        RAISE EXCEPTION 'webhook_events: processed_at deja fixe, modification interdite'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_webhook_events_protect ON webhook_events;
CREATE TRIGGER trg_webhook_events_protect
    BEFORE UPDATE OR DELETE ON webhook_events
    FOR EACH ROW EXECUTE FUNCTION fn_webhook_events_protect();


-- ---------------------------------------------------------------------------
-- 4) mandates : chain_hash/prev_hash/payload_hash/signed_at immuables ;
--    revoked_at, revocation_reason, audit_log peuvent etre mis a jour
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_mandates_protect() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'mandates: DELETE bloque (chaine immuable)'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- UPDATE : champs critiques de la chaine
    IF NEW.chain_hash       IS DISTINCT FROM OLD.chain_hash
       OR NEW.prev_hash       IS DISTINCT FROM OLD.prev_hash
       OR NEW.payload_hash    IS DISTINCT FROM OLD.payload_hash
       OR NEW.signed_at       IS DISTINCT FROM OLD.signed_at
       OR NEW.mandate_id      IS DISTINCT FROM OLD.mandate_id
       OR NEW.mandate_type    IS DISTINCT FROM OLD.mandate_type
       OR NEW.principal_id    IS DISTINCT FROM OLD.principal_id
       OR NEW.agent_identity  IS DISTINCT FROM OLD.agent_identity
       OR NEW.scope_json      IS DISTINCT FROM OLD.scope_json
    THEN
        RAISE EXCEPTION 'mandates: chaine immuable, champ critique modifie'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    -- revoked_at une fois fixe ne peut pas etre revert
    IF OLD.revoked_at IS NOT NULL
       AND (NEW.revoked_at IS NULL
            OR NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
    THEN
        RAISE EXCEPTION 'mandates: revocation immuable une fois enregistree'
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_mandates_protect ON mandates;
CREATE TRIGGER trg_mandates_protect
    BEFORE UPDATE OR DELETE ON mandates
    FOR EACH ROW EXECUTE FUNCTION fn_mandates_protect();


-- ---------------------------------------------------------------------------
-- 5) Verification helper : recense les triggers actifs
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_audit_immutability_status AS
SELECT
    event_object_table AS table_name,
    trigger_name,
    array_agg(event_manipulation ORDER BY event_manipulation) AS events,
    action_timing
FROM information_schema.triggers
WHERE trigger_name LIKE 'trg_%_protect'
   OR trigger_name LIKE 'trg_%_no_update'
GROUP BY event_object_table, trigger_name, action_timing;


-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9J
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9j_audit_immutability","version":"9.0.0-phase9j","date":"2026-04-30","triggers":["admin_actions","ai_decisions_log","hostinger_audit","direct_links_audit","webhook_events","mandates"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_042_v9_audit_immutability',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9J audit immutability sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 043 : V9 Phase 9-BOOT — self-bootstrap state
-- 2026-04-29
--
-- Tables :
--   self_bootstrap_state  : phase d'amorcage (init, validators, plans, complete)
--   service_activations   : 1 ligne par service tiers (Cloudflare, Stripe, ...)
--   handoff_pending       : handoffs KYC / carte / etape manuelle
--
-- Numerotation 043 : reservee dans le master plan V9 (037-042 = autres phases).

-- ---------------------------------------------------------------------------
-- 1) self_bootstrap_state : phases successives de l'amorcage
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS self_bootstrap_state (
    id              BIGSERIAL PRIMARY KEY,
    bootstrap_id    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    phase           TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending','in_progress','blocked','done','failed')),
    detail_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sbs_phase_status
    ON self_bootstrap_state(phase, status, started_at DESC);

-- ---------------------------------------------------------------------------
-- 2) service_activations : etat operationnel de chaque integration tierce
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS service_activations (
    id                BIGSERIAL PRIMARY KEY,
    service_name      TEXT NOT NULL UNIQUE,
    tier              INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 3),
    activation_status TEXT NOT NULL CHECK (activation_status IN
                          ('queued','planning','awaiting_handoff','active','failed')),
    plan_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    vault_path        TEXT,
    last_attempt_at   TIMESTAMPTZ,
    activated_at      TIMESTAMPTZ,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_activations_status
    ON service_activations(activation_status, tier);

CREATE INDEX IF NOT EXISTS idx_service_activations_active_recent
    ON service_activations(activated_at DESC) WHERE activation_status = 'active';

-- ---------------------------------------------------------------------------
-- 3) handoff_pending : magic-link en attente de validation humaine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS handoff_pending (
    id                  BIGSERIAL PRIMARY KEY,
    handoff_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    handoff_type        TEXT NOT NULL CHECK (handoff_type IN ('kyc','card','manual_step')),
    target_email        TEXT NOT NULL,
    magic_link_token    TEXT NOT NULL UNIQUE,
    instructions_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    locale              TEXT NOT NULL DEFAULT 'en',
    status              TEXT NOT NULL DEFAULT 'pending' CHECK (status IN
                            ('pending','reminded_1h','reminded_12h','reminded_24h',
                             'escalated','resolved','expired')),
    expires_at          TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_status
    ON handoff_pending(status, expires_at);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_open
    ON handoff_pending(created_at DESC)
    WHERE status NOT IN ('resolved','expired');

-- ---------------------------------------------------------------------------
-- 4) Seal V9 Phase 9-BOOT dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9boot_self_bootstrap","version":"9.0.0-bootstrap","date":"2026-04-29","tables":["self_bootstrap_state","service_activations","handoff_pending"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_043_v9_bootstrap',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9-BOOT self_bootstrap sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 044 : V9 Phase 9-BOOT — mandats numeriques eIDAS Article 26
-- 2026-04-29
--
-- Chaque mandat est un maillon d'une chaine SHA-256 :
--   chain_hash = sha256(prev_hash || payload_hash)
-- La revocation est append-only via le champ audit_log (jamais de DELETE).

CREATE TABLE IF NOT EXISTS mandates (
    id                 BIGSERIAL PRIMARY KEY,
    mandate_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    mandate_type       TEXT NOT NULL CHECK (mandate_type IN
                          ('account_creation','sub_authorization',
                           'data_processing','payment_authorization')),
    principal_id       TEXT NOT NULL,
    agent_identity     TEXT NOT NULL,
    scope_json         JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash       TEXT NOT NULL,
    prev_hash          TEXT NOT NULL,
    chain_hash         TEXT NOT NULL UNIQUE,
    signed_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ,
    revoked_at         TIMESTAMPTZ,
    revocation_reason  TEXT,
    audit_log          JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_mandates_chain_hash    ON mandates(chain_hash);
CREATE INDEX IF NOT EXISTS idx_mandates_signed_at     ON mandates(signed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mandates_principal     ON mandates(principal_id, signed_at DESC);
CREATE INDEX IF NOT EXISTS idx_mandates_active
    ON mandates(principal_id) WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_mandates_type_recent
    ON mandates(mandate_type, signed_at DESC);

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9-BOOT (mandates) dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9boot_mandates_eidas","version":"9.0.0-bootstrap","date":"2026-04-29","standard":"eIDAS Article 26","table":"mandates"}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_044_v9_mandates',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9-BOOT mandates sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 045 : V9 Phase 9B — Setup Wizard Ahmed (admin bootstrap, 4 etapes)
-- 2026-04-30
--
-- Tables :
--   setup_wizard_state  : 1 ligne par session de wizard (historique)
--   platform_config     : singleton (id=1) — config commitee active
--
-- Numero 045 et non 038 : 037 deja pose (Phase 9A direct_links), 038-042
-- reserves au master plan (billing 9H, hostinger 9G, ai 9D, pricing 9C,
-- audit 9J), 043-044 deja poses (Phase 9-BOOT). 045 = prochain libre.
-- ADR-10 documente ce choix.

-- ---------------------------------------------------------------------------
-- 1) setup_wizard_state : sessions de wizard (multi-tentative tolere)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS setup_wizard_state (
    id                    BIGSERIAL PRIMARY KEY,
    wizard_id             UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    current_step          TEXT NOT NULL CHECK (current_step IN
                              ('brand_identity','pricing_baseline',
                               'service_catalog','operations_defaults')),
    completed_steps       TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    partial_config_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                TEXT NOT NULL DEFAULT 'in_progress'
                              CHECK (status IN
                                  ('in_progress','committed','abandoned')),
    started_by            TEXT NOT NULL DEFAULT 'ahmed',
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    committed_at          TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_setup_wizard_state_status
    ON setup_wizard_state(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_setup_wizard_state_in_progress
    ON setup_wizard_state(updated_at DESC)
    WHERE status = 'in_progress';

-- ---------------------------------------------------------------------------
-- 2) platform_config : singleton (1 seule ligne, id=1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS platform_config (
    id                BIGINT PRIMARY KEY CHECK (id = 1),
    version           INTEGER NOT NULL DEFAULT 1,
    identity_json     JSONB NOT NULL,
    pricing_json      JSONB NOT NULL,
    services_json     JSONB NOT NULL,
    operations_json   JSONB NOT NULL,
    committed_by      TEXT NOT NULL,
    committed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Vue d'historique : on garde aussi `setup_wizard_state` qui contient
-- toutes les tentatives anterieures (incluant abandonees).

-- ---------------------------------------------------------------------------
-- 3) Seal V9 Phase 9B dans evidence_ledger
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9b_setup_wizard","version":"9.0.0-phase9b","date":"2026-04-30","tables":["setup_wizard_state","platform_config"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_045_v9_setup_wizard',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9B setup_wizard sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 046 : V9 Phase 9E — Handoff Orchestrator unifie
-- 2026-04-30
--
-- Table unique pour TOUS les handoffs hors service activation (qui reste
-- gere par `handoff_pending` 9-BOOT). Reference le direct_link sous-jacent
-- (FK informelle vers `direct_links.link_id`).
--
-- Numero 046 : prochain libre apres 045 (ADR-15).

CREATE TABLE IF NOT EXISTS handoff_requests (
    id                       BIGSERIAL PRIMARY KEY,
    handoff_id               UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id               TEXT NOT NULL,
    action_type              TEXT NOT NULL,                 -- ref catalog 9A
    state                    TEXT NOT NULL DEFAULT 'requested'
                                CHECK (state IN ('requested','notified',
                                    'acknowledged','resolved','expired',
                                    'escalated','cancelled')),
    target_email             TEXT NOT NULL,
    locale                   TEXT NOT NULL DEFAULT 'en',
    direct_link_id           UUID NOT NULL REFERENCES direct_links(link_id),
    payload_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    title                    TEXT NOT NULL,
    body                     TEXT NOT NULL,
    cta_url                  TEXT NOT NULL,
    expires_at               TIMESTAMPTZ NOT NULL,
    reminders_sent           INTEGER NOT NULL DEFAULT 0,
    resolved_at              TIMESTAMPTZ,
    resolution_payload_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_req_project_recent
    ON handoff_requests(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_state_recent
    ON handoff_requests(state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_open_expires
    ON handoff_requests(expires_at)
    WHERE state IN ('requested','notified','acknowledged','escalated');

CREATE INDEX IF NOT EXISTS idx_handoff_req_action_type_recent
    ON handoff_requests(action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_link
    ON handoff_requests(direct_link_id);

-- ---------------------------------------------------------------------------
-- Vue : handoffs ouverts par projet (pour dashboard)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_handoff_open AS
SELECT
    project_id,
    action_type,
    COUNT(*) AS open_count,
    SUM(CASE WHEN state = 'escalated' THEN 1 ELSE 0 END)::INT AS escalated_count,
    MIN(created_at) AS oldest_open
FROM handoff_requests
WHERE state IN ('requested','notified','acknowledged','escalated')
GROUP BY project_id, action_type;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9E
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9e_handoff_orchestrator","version":"9.0.0-phase9e","date":"2026-04-30","tables":["handoff_requests"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_046_v9_handoff_orchestrator',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9E handoff_orchestrator sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 047 : V9 Phase 9F — Client Onboarding + table canonique `projects`
-- 2026-04-30
--
-- Tables :
--   projects                      : table CANONIQUE des projets clients
--   client_onboarding_sessions    : sessions du wizard client (6 etapes)
--
-- ⚠ FK retroactives sur 9C/9D/9E : reportees en Phase 9P. Pour l'instant,
--   `intelligence_qualifications.project_id`, `intelligence_pricings.project_id`,
--   `intelligence_assemblies.project_id`, `project_progression.project_id`,
--   `handoff_requests.project_id`, `ai_decisions_log.project_id` restent en
--   TEXT libre. ADR-15 documente le choix.

-- ---------------------------------------------------------------------------
-- 1) projects (canonique)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id              BIGSERIAL PRIMARY KEY,
    project_id      UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner_email     TEXT NOT NULL,
    company_name    TEXT NOT NULL,
    country         CHAR(2) NOT NULL,
    locale          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    pack_id_hint    TEXT NOT NULL,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'submitted'
                       CHECK (status IN ('submitted','qualifying','assembled',
                                          'paywall_pending','in_production',
                                          'delivered','archived','cancelled')),
    summary_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_projects_owner_recent
    ON projects(owner_email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_projects_status_recent
    ON projects(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_projects_active
    ON projects(updated_at DESC)
    WHERE archived_at IS NULL AND status NOT IN ('cancelled','delivered');

CREATE INDEX IF NOT EXISTS idx_projects_pack
    ON projects(pack_id_hint, created_at DESC);

-- ---------------------------------------------------------------------------
-- 2) client_onboarding_sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS client_onboarding_sessions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    current_step        TEXT NOT NULL CHECK (current_step IN
                            ('identity','project_brief','pack_selection',
                             'branding','technical_preferences','review_submit')),
    completed_steps     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    partial_data_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'in_progress'
                            CHECK (status IN ('in_progress','submitted','abandoned')),
    owner_email         TEXT,
    project_id          UUID REFERENCES projects(project_id),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cos_status_recent
    ON client_onboarding_sessions(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_cos_in_progress
    ON client_onboarding_sessions(updated_at DESC)
    WHERE status = 'in_progress';

CREATE INDEX IF NOT EXISTS idx_cos_owner_email
    ON client_onboarding_sessions(owner_email, started_at DESC)
    WHERE owner_email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) Vue dashboard funnel (combien de sessions a quelle etape, taux de submit)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_onboarding_funnel AS
SELECT
    current_step,
    COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
    COUNT(*) FILTER (WHERE status = 'abandoned')   AS abandoned,
    COUNT(*) FILTER (WHERE status = 'submitted')   AS submitted
FROM client_onboarding_sessions
GROUP BY current_step;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9F
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9f_client_onboarding","version":"9.0.0-phase9f","date":"2026-04-30","tables":["projects","client_onboarding_sessions"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_047_v9_client_onboarding',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9F client_onboarding sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 048 : V9 Phase 9N — Admin actions audit (overrides, FinOps changes, etc.)
-- 2026-04-30
--
-- 1 ligne par action de l'admin (Ahmed) qui mute un etat. Trace immuable
-- (append-only — un trigger sera ajoute en Phase 9J pour bloquer
-- UPDATE/DELETE).

CREATE TABLE IF NOT EXISTS admin_actions (
    id              BIGSERIAL PRIMARY KEY,
    action_id       UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    admin_id        TEXT NOT NULL,
    action_type     TEXT NOT NULL,                    -- e.g. 'cancel_handoff', 'override_router_policy'
    target_type     TEXT NOT NULL,                    -- e.g. 'handoff', 'project', 'direct_link'
    target_id       TEXT,                             -- UUID ou identifiant metier
    payload_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    token_hint      TEXT,                             -- 4 derniers chars du token, jamais le brut
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_actions_admin_recent
    ON admin_actions(admin_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_actions_type_recent
    ON admin_actions(action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_admin_actions_target
    ON admin_actions(target_type, target_id, created_at DESC)
    WHERE target_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Vue : derniere action par admin et par target
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_admin_actions_recent AS
SELECT action_id, admin_id, action_type, target_type, target_id,
       payload_json, created_at
  FROM admin_actions
 ORDER BY created_at DESC
 LIMIT 500;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9N
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9n_admin_dashboard","version":"9.0.0-phase9n","date":"2026-04-30","tables":["admin_actions"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_048_v9_admin_dashboard',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9N admin_dashboard sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 049 : V9 Phase 9P — Consolidation FK + injection liens directs livrables
-- 2026-04-30
--
-- Ferme ADR-15 (FK retroactives project_id) et partiellement ADR-08
-- (handoff_pending.direct_link_id nullable ; magic_link_token reste pour
-- la fenetre de depreciation).
--
-- Strategie data-aware :
-- 1. Pour chaque table dependante avec project_id TEXT :
--    a. DELETE des lignes orphelines (project_id qui ne match aucune
--       row dans projects.project_id::text)
--    b. ALTER COLUMN project_id TYPE UUID USING project_id::uuid
--    c. ADD CONSTRAINT FK -> projects(project_id)
-- 2. handoff_pending : ADD direct_link_id UUID nullable FK direct_links

-- ---------------------------------------------------------------------------
-- 1. Cleanup orphans + ALTER COLUMN + ADD FK
-- ---------------------------------------------------------------------------

-- intelligence_qualifications (Phase 9C)
DELETE FROM intelligence_qualifications
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_qualifications
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_qualifications
    ADD CONSTRAINT fk_iq_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- intelligence_pricings (Phase 9C)
DELETE FROM intelligence_pricings
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_pricings
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_pricings
    ADD CONSTRAINT fk_ip_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- intelligence_assemblies (Phase 9C)
DELETE FROM intelligence_assemblies
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE intelligence_assemblies
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE intelligence_assemblies
    ADD CONSTRAINT fk_ia_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- project_progression (Phase 9C)
DELETE FROM project_progression
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE project_progression
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE project_progression
    ADD CONSTRAINT fk_pp_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- handoff_requests (Phase 9E)
DELETE FROM handoff_requests
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE handoff_requests
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE handoff_requests
    ADD CONSTRAINT fk_hr_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- ai_decisions_log (Phase 9D)
DELETE FROM ai_decisions_log
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE ai_decisions_log
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE ai_decisions_log
    ADD CONSTRAINT fk_aidl_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- hostinger_resources (Phase 9G)
DELETE FROM hostinger_resources
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE hostinger_resources
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE hostinger_resources
    ADD CONSTRAINT fk_hres_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- payments (Phase 9H)
DELETE FROM payments
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE payments
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE payments
    ADD CONSTRAINT fk_payments_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- backups (Phase 9G — project_id est TEXT)
DELETE FROM backups
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE backups
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE backups
    ADD CONSTRAINT fk_backups_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- ssl_certificates (Phase 9G)
DELETE FROM ssl_certificates
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE ssl_certificates
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE ssl_certificates
    ADD CONSTRAINT fk_ssl_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);

-- invoices (Phase 9H)
DELETE FROM invoices
 WHERE project_id NOT IN (SELECT project_id::text FROM projects);
ALTER TABLE invoices
    ALTER COLUMN project_id TYPE UUID USING project_id::uuid;
ALTER TABLE invoices
    ADD CONSTRAINT fk_invoices_project
    FOREIGN KEY (project_id) REFERENCES projects(project_id);


-- ---------------------------------------------------------------------------
-- 2. handoff_pending : ajout direct_link_id nullable FK
-- ---------------------------------------------------------------------------
-- Migration partielle : la colonne magic_link_token reste (deprecation
-- window). Une migration future supprimera magic_link_token + rendra
-- direct_link_id NOT NULL.
ALTER TABLE handoff_pending
    ADD COLUMN IF NOT EXISTS direct_link_id UUID
        REFERENCES direct_links(link_id);

CREATE INDEX IF NOT EXISTS idx_handoff_pending_direct_link
    ON handoff_pending(direct_link_id)
    WHERE direct_link_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- 3. Vue dashboard : projets avec leur etat consolide cross-tables
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_project_consolidated_status AS
SELECT
    p.project_id,
    p.owner_email,
    p.title,
    p.status                                                AS project_status,
    p.pack_id_hint,
    (SELECT COUNT(*) FROM intelligence_qualifications q
        WHERE q.project_id = p.project_id)                  AS qualifications_count,
    (SELECT MAX(created_at) FROM intelligence_pricings ip
        WHERE ip.project_id = p.project_id)                 AS last_pricing_at,
    (SELECT bool_or(paywall_triggered_at IS NOT NULL)
       FROM project_progression pp
        WHERE pp.project_id = p.project_id)                 AS paywall_triggered,
    (SELECT COUNT(*) FROM handoff_requests h
        WHERE h.project_id = p.project_id
          AND h.state IN ('requested','notified','acknowledged','escalated'))
                                                            AS open_handoffs,
    (SELECT SUM(amount_cents) FROM payments pay
        WHERE pay.project_id = p.project_id
          AND pay.status = 'succeeded')                     AS paid_amount_cents,
    (SELECT COUNT(*) FROM hostinger_resources hr
        WHERE hr.project_id = p.project_id
          AND hr.status = 'active')                         AS active_infra_resources,
    (SELECT SUM(cost_usd) FROM ai_decisions_log ad
        WHERE ad.project_id = p.project_id)                 AS total_ai_cost_usd
FROM projects p;


-- ---------------------------------------------------------------------------
-- 4. Seal V9 Phase 9P
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9p_consolidation","version":"9.0.0-phase9p","date":"2026-04-30","fk_added":["intelligence_qualifications","intelligence_pricings","intelligence_assemblies","project_progression","handoff_requests","ai_decisions_log","hostinger_resources","payments","backups","ssl_certificates","invoices"],"partial":["handoff_pending.direct_link_id"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_049_v9_consolidation',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9P consolidation sealed (chain_hash=%)', new_chain_hash;
END
$$;
-- 050 : V9 Phase 9I — Legal Framework (GDPR + consent + erasure + export)
-- 2026-04-30
--
-- 3 tables :
--   user_consents          : record consents avec versioning + revocation
--   data_export_requests   : trace les exports GDPR Art 20
--   data_erasure_requests  : trace les demandes d'oubli Art 17 + retention 30j

-- ---------------------------------------------------------------------------
-- 1) user_consents : 1 row par (owner_email, scope) avec history
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_consents (
    id                  BIGSERIAL PRIMARY KEY,
    consent_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner_email         TEXT NOT NULL,                             -- lowercase
    scope               TEXT NOT NULL CHECK (scope IN
                            ('tos_acceptance','privacy_policy',
                             'cookie_functional','cookie_analytics',
                             'cookie_marketing','data_processing',
                             'marketing_opt_in')),
    doc_version         TEXT NOT NULL,
    accepted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at          TIMESTAMPTZ,
    revocation_reason   TEXT,
    ip_hash             TEXT,                                      -- SHA-256
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_consents_owner_recent
    ON user_consents(owner_email, accepted_at DESC);

CREATE INDEX IF NOT EXISTS idx_consents_active
    ON user_consents(owner_email, scope)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_consents_scope_recent
    ON user_consents(scope, accepted_at DESC);


-- ---------------------------------------------------------------------------
-- 2) data_export_requests : Article 20 GDPR (right to data portability)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_export_requests (
    id                BIGSERIAL PRIMARY KEY,
    request_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id        UUID NOT NULL REFERENCES projects(project_id),
    requester_email   TEXT,
    record_counts_json JSONB,
    status            TEXT NOT NULL DEFAULT 'completed'
                          CHECK (status IN ('completed','failed')),
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    error_msg         TEXT
);

CREATE INDEX IF NOT EXISTS idx_export_project_recent
    ON data_export_requests(project_id, requested_at DESC);


-- ---------------------------------------------------------------------------
-- 3) data_erasure_requests : Article 17 GDPR (right to be forgotten)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_erasure_requests (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          UUID NOT NULL REFERENCES projects(project_id),
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','executed',
                                               'cancelled','blocked')),
    reason              TEXT NOT NULL,
    requester_email     TEXT,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executable_after    TIMESTAMPTZ NOT NULL,                       -- requested + 30j
    executed_at         TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    counts_json         JSONB,                                       -- rows touchees
    legal_hold_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_erasure_project
    ON data_erasure_requests(project_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_erasure_pending_due
    ON data_erasure_requests(executable_after)
    WHERE status = 'pending';


-- ---------------------------------------------------------------------------
-- 4) Vue : tableau de bord conformite GDPR
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_gdpr_compliance AS
SELECT
    'consents' AS metric,
    COUNT(*) FILTER (WHERE revoked_at IS NULL)::INT AS active,
    COUNT(*) FILTER (WHERE revoked_at IS NOT NULL)::INT AS revoked
  FROM user_consents
UNION ALL
SELECT
    'erasure_requests',
    COUNT(*) FILTER (WHERE status = 'pending')::INT,
    COUNT(*) FILTER (WHERE status = 'executed')::INT
  FROM data_erasure_requests;


-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9I
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9i_legal_framework","version":"9.0.0-phase9i","date":"2026-04-30","tables":["user_consents","data_export_requests","data_erasure_requests"],"compliance":["GDPR Art 6","Art 17","Art 20"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_050_v9_legal_framework',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9I legal_framework sealed (chain_hash=%)', new_chain_hash;
END
$$;
