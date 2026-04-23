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
