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
