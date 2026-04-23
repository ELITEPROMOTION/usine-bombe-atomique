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
