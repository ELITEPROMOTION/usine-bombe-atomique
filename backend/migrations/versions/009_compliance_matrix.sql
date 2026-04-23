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
