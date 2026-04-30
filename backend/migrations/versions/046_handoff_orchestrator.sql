-- 046 : V9 Phase 9E — Handoff Orchestrator unifie
-- 2026-04-30
--
-- Table unique pour TOUS les handoffs hors service activation (qui reste
-- gere par `handoff_pending` 9-BOOT). Reference le direct_link sous-jacent
-- (FK informelle vers `direct_links.link_id`).
--
-- Numero 046 : prochain libre apres 045 (ADR-15).

CREATE TABLE IF NOT EXISTS handoff_requests (
    id                       BIGSERIAL PRIMARY KEY,
    handoff_id               UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id               TEXT NOT NULL,
    action_type              TEXT NOT NULL,                 -- ref catalog 9A
    state                    TEXT NOT NULL DEFAULT 'requested'
                                CHECK (state IN ('requested','notified',
                                    'acknowledged','resolved','expired',
                                    'escalated','cancelled')),
    target_email             TEXT NOT NULL,
    locale                   TEXT NOT NULL DEFAULT 'en',
    direct_link_id           UUID NOT NULL REFERENCES direct_links(link_id),
    payload_json             JSONB NOT NULL DEFAULT '{}'::jsonb,
    title                    TEXT NOT NULL,
    body                     TEXT NOT NULL,
    cta_url                  TEXT NOT NULL,
    expires_at               TIMESTAMPTZ NOT NULL,
    reminders_sent           INTEGER NOT NULL DEFAULT 0,
    resolved_at              TIMESTAMPTZ,
    resolution_payload_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_handoff_req_project_recent
    ON handoff_requests(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_state_recent
    ON handoff_requests(state, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_open_expires
    ON handoff_requests(expires_at)
    WHERE state IN ('requested','notified','acknowledged','escalated');

CREATE INDEX IF NOT EXISTS idx_handoff_req_action_type_recent
    ON handoff_requests(action_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_handoff_req_link
    ON handoff_requests(direct_link_id);

-- ---------------------------------------------------------------------------
-- Vue : handoffs ouverts par projet (pour dashboard)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_handoff_open AS
SELECT
    project_id,
    action_type,
    COUNT(*) AS open_count,
    SUM(CASE WHEN state = 'escalated' THEN 1 ELSE 0 END)::INT AS escalated_count,
    MIN(created_at) AS oldest_open
FROM handoff_requests
WHERE state IN ('requested','notified','acknowledged','escalated')
GROUP BY project_id, action_type;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9E
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

    seal_payload := '{"event":"v9_phase9e_handoff_orchestrator","version":"9.0.0-phase9e","date":"2026-04-30","tables":["handoff_requests"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_046_v9_handoff_orchestrator',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9E handoff_orchestrator sealed (chain_hash=%)', new_chain_hash;
END
$$;
