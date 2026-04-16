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
