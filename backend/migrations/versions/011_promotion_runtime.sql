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
