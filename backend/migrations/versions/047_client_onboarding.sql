-- 047 : V9 Phase 9F — Client Onboarding + table canonique `projects`
-- 2026-04-30
--
-- Tables :
--   projects                      : table CANONIQUE des projets clients
--   client_onboarding_sessions    : sessions du wizard client (6 etapes)
--
-- ⚠ FK retroactives sur 9C/9D/9E : reportees en Phase 9P. Pour l'instant,
--   `intelligence_qualifications.project_id`, `intelligence_pricings.project_id`,
--   `intelligence_assemblies.project_id`, `project_progression.project_id`,
--   `handoff_requests.project_id`, `ai_decisions_log.project_id` restent en
--   TEXT libre. ADR-15 documente le choix.

-- ---------------------------------------------------------------------------
-- 1) projects (canonique)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id              BIGSERIAL PRIMARY KEY,
    project_id      UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    owner_email     TEXT NOT NULL,
    company_name    TEXT NOT NULL,
    country         CHAR(2) NOT NULL,
    locale          TEXT NOT NULL,
    currency        TEXT NOT NULL,
    pack_id_hint    TEXT NOT NULL,
    title           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'submitted'
                       CHECK (status IN ('submitted','qualifying','assembled',
                                          'paywall_pending','in_production',
                                          'delivered','archived','cancelled')),
    summary_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_projects_owner_recent
    ON projects(owner_email, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_projects_status_recent
    ON projects(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_projects_active
    ON projects(updated_at DESC)
    WHERE archived_at IS NULL AND status NOT IN ('cancelled','delivered');

CREATE INDEX IF NOT EXISTS idx_projects_pack
    ON projects(pack_id_hint, created_at DESC);

-- ---------------------------------------------------------------------------
-- 2) client_onboarding_sessions
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS client_onboarding_sessions (
    id                  BIGSERIAL PRIMARY KEY,
    session_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    current_step        TEXT NOT NULL CHECK (current_step IN
                            ('identity','project_brief','pack_selection',
                             'branding','technical_preferences','review_submit')),
    completed_steps     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    partial_data_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              TEXT NOT NULL DEFAULT 'in_progress'
                            CHECK (status IN ('in_progress','submitted','abandoned')),
    owner_email         TEXT,
    project_id          UUID REFERENCES projects(project_id),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_cos_status_recent
    ON client_onboarding_sessions(status, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_cos_in_progress
    ON client_onboarding_sessions(updated_at DESC)
    WHERE status = 'in_progress';

CREATE INDEX IF NOT EXISTS idx_cos_owner_email
    ON client_onboarding_sessions(owner_email, started_at DESC)
    WHERE owner_email IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 3) Vue dashboard funnel (combien de sessions a quelle etape, taux de submit)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_onboarding_funnel AS
SELECT
    current_step,
    COUNT(*) FILTER (WHERE status = 'in_progress') AS in_progress,
    COUNT(*) FILTER (WHERE status = 'abandoned')   AS abandoned,
    COUNT(*) FILTER (WHERE status = 'submitted')   AS submitted
FROM client_onboarding_sessions
GROUP BY current_step;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9F
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

    seal_payload := '{"event":"v9_phase9f_client_onboarding","version":"9.0.0-phase9f","date":"2026-04-30","tables":["projects","client_onboarding_sessions"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_047_v9_client_onboarding',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9F client_onboarding sealed (chain_hash=%)', new_chain_hash;
END
$$;
