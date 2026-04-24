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
