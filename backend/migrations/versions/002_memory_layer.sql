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
