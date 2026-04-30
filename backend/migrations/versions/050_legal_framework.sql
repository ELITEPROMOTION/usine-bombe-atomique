-- 050 : V9 Phase 9I — Legal Framework (GDPR + consent + erasure + export)
-- 2026-04-30
--
-- 3 tables :
--   user_consents          : record consents avec versioning + revocation
--   data_export_requests   : trace les exports GDPR Art 20
--   data_erasure_requests  : trace les demandes d'oubli Art 17 + retention 30j

-- ---------------------------------------------------------------------------
-- 1) user_consents : 1 row par (owner_email, scope) avec history
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_consents (
    id                  BIGSERIAL PRIMARY KEY,
    consent_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner_email         TEXT NOT NULL,                             -- lowercase
    scope               TEXT NOT NULL CHECK (scope IN
                            ('tos_acceptance','privacy_policy',
                             'cookie_functional','cookie_analytics',
                             'cookie_marketing','data_processing',
                             'marketing_opt_in')),
    doc_version         TEXT NOT NULL,
    accepted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at          TIMESTAMPTZ,
    revocation_reason   TEXT,
    ip_hash             TEXT,                                      -- SHA-256
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_consents_owner_recent
    ON user_consents(owner_email, accepted_at DESC);

CREATE INDEX IF NOT EXISTS idx_consents_active
    ON user_consents(owner_email, scope)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_consents_scope_recent
    ON user_consents(scope, accepted_at DESC);


-- ---------------------------------------------------------------------------
-- 2) data_export_requests : Article 20 GDPR (right to data portability)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_export_requests (
    id                BIGSERIAL PRIMARY KEY,
    request_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id        UUID NOT NULL REFERENCES projects(project_id),
    requester_email   TEXT,
    record_counts_json JSONB,
    status            TEXT NOT NULL DEFAULT 'completed'
                          CHECK (status IN ('completed','failed')),
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at      TIMESTAMPTZ,
    error_msg         TEXT
);

CREATE INDEX IF NOT EXISTS idx_export_project_recent
    ON data_export_requests(project_id, requested_at DESC);


-- ---------------------------------------------------------------------------
-- 3) data_erasure_requests : Article 17 GDPR (right to be forgotten)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS data_erasure_requests (
    id                  BIGSERIAL PRIMARY KEY,
    request_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          UUID NOT NULL REFERENCES projects(project_id),
    status              TEXT NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','executed',
                                               'cancelled','blocked')),
    reason              TEXT NOT NULL,
    requester_email     TEXT,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executable_after    TIMESTAMPTZ NOT NULL,                       -- requested + 30j
    executed_at         TIMESTAMPTZ,
    cancelled_at        TIMESTAMPTZ,
    counts_json         JSONB,                                       -- rows touchees
    legal_hold_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_erasure_project
    ON data_erasure_requests(project_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_erasure_pending_due
    ON data_erasure_requests(executable_after)
    WHERE status = 'pending';


-- ---------------------------------------------------------------------------
-- 4) Vue : tableau de bord conformite GDPR
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_gdpr_compliance AS
SELECT
    'consents' AS metric,
    COUNT(*) FILTER (WHERE revoked_at IS NULL)::INT AS active,
    COUNT(*) FILTER (WHERE revoked_at IS NOT NULL)::INT AS revoked
  FROM user_consents
UNION ALL
SELECT
    'erasure_requests',
    COUNT(*) FILTER (WHERE status = 'pending')::INT,
    COUNT(*) FILTER (WHERE status = 'executed')::INT
  FROM data_erasure_requests;


-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9I
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    last_chain_hash TEXT;
    new_payload_hash TEXT;
    new_chain_hash TEXT;
    seal_payload TEXT;
BEGIN
    SELECT chain_hash INTO last_chain_hash
    FROM evidence_ledger ORDER BY id DESC LIMIT 1;

    IF last_chain_hash IS NULL THEN
        last_chain_hash := repeat('0', 64);
    END IF;

    seal_payload := '{"event":"v9_phase9i_legal_framework","version":"9.0.0-phase9i","date":"2026-04-30","tables":["user_consents","data_export_requests","data_erasure_requests"],"compliance":["GDPR Art 6","Art 17","Art 20"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_050_v9_legal_framework',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9I legal_framework sealed (chain_hash=%)', new_chain_hash;
END
$$;
