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
