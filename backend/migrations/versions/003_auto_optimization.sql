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
