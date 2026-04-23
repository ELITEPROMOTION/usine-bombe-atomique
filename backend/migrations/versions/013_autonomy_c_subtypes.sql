-- ============================================================
-- 013_autonomy_c_subtypes.sql - V5.1
-- Decompose Type C en 6 sous-types C1..C6 (vraies zones d'ambiguite)
-- + Registre d'ambiguite + lease permissions + hard boundaries
-- ============================================================

-- Type C split : C1..C6
ALTER TABLE pending_user_inputs
    ADD COLUMN IF NOT EXISTS c_sub_type VARCHAR(4);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chk_c_sub_type') THEN
        ALTER TABLE pending_user_inputs
            ADD CONSTRAINT chk_c_sub_type
            CHECK (c_sub_type IS NULL OR c_sub_type IN
                   ('C1','C2','C3','C4','C5','C6'));
    END IF;
END $$;

-- Ambiguity ledger : trace chaque resolution d'ambiguite
CREATE TABLE IF NOT EXISTS ambiguity_ledger (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    correlation_id VARCHAR(64),
    level INTEGER NOT NULL,          -- 1=doc/repo, 2=industry, 3=bounded sim, 4=ask
    resolved BOOLEAN NOT NULL,
    kind VARCHAR(30) NOT NULL,       -- semantic|factual|value|strategic|false|self_induced
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    ask_skipped BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ambiguity_task
    ON ambiguity_ledger(task_id, created_at DESC);

-- Permission leases : scope + cap + duration + auto-expiry
CREATE TABLE IF NOT EXISTS permission_leases (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    scope VARCHAR(120) NOT NULL,      -- ex: "payment.datadog"
    cap_amount DECIMAL(14,4),
    cap_currency VARCHAR(10),
    granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    usage_count INTEGER NOT NULL DEFAULT 0,
    usage_cap INTEGER NOT NULL DEFAULT 1,
    granter VARCHAR(120) NOT NULL DEFAULT 'ahmed'
);
CREATE INDEX IF NOT EXISTS idx_lease_scope_active
    ON permission_leases(scope, expires_at)
    WHERE revoked_at IS NULL;

-- Hard boundaries : scopes qui DOIVENT escalader (paiement, rollback prod, RGPD...)
CREATE TABLE IF NOT EXISTS hard_boundary_registry (
    scope VARCHAR(120) PRIMARY KEY,
    description TEXT NOT NULL,
    requires_type VARCHAR(1) NOT NULL
        CHECK (requires_type IN ('A','B','C')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO hard_boundary_registry(scope, description, requires_type) VALUES
    ('payment.any', 'Tout paiement direct vers un fournisseur', 'B'),
    ('credentials.new_account', 'Creation compte externe exigeant identite', 'A'),
    ('prod.rollback_last_resort', 'Rollback prod apres epuisement des patches', 'C'),
    ('gdpr.waiver', 'Derogation donnee personnelle RGPD', 'C'),
    ('dendani.reputation_risk', 'Action a risque reputationnel Dendani', 'C')
ON CONFLICT (scope) DO NOTHING;
