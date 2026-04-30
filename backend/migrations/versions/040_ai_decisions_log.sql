-- 040 : V9 Phase 9D — journalisation des decisions IA
-- 2026-04-30
--
-- 1 ligne par appel via `AIRouter.route()`. Sert :
-- - au CostGuard pour calculer la depense cumulee par projet et par jour
-- - au dashboard FinOps pour visualiser le cout reel par projet
-- - a l'analyse post-mortem (loops, fallbacks, erreurs)

CREATE TABLE IF NOT EXISTS ai_decisions_log (
    id                  BIGSERIAL PRIMARY KEY,
    decision_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    requested_provider  TEXT NOT NULL,
    actual_provider     TEXT NOT NULL,
    status              TEXT NOT NULL CHECK (status IN
                            ('ok','fallback','error',
                             'budget_blocked','loop_blocked')),
    prompt_hash         TEXT NOT NULL,                  -- sha256 du prompt
    prompt_preview      TEXT,                           -- 200 premiers chars (debug)
    response_preview    TEXT,                           -- 200 premiers chars (debug)
    tokens_in           INTEGER NOT NULL DEFAULT 0,
    tokens_out          INTEGER NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms          INTEGER NOT NULL DEFAULT 0,
    fallback_used       BOOLEAN NOT NULL DEFAULT FALSE,
    retries             INTEGER NOT NULL DEFAULT 0,
    loop_detected       BOOLEAN NOT NULL DEFAULT FALSE,
    error_msg           TEXT,
    metadata_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_dec_project_recent
    ON ai_decisions_log(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_status_recent
    ON ai_decisions_log(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_actual_provider_recent
    ON ai_decisions_log(actual_provider, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ai_dec_cost_window
    ON ai_decisions_log(created_at DESC, cost_usd);

CREATE INDEX IF NOT EXISTS idx_ai_dec_loop_recent
    ON ai_decisions_log(created_at DESC)
    WHERE loop_detected = TRUE;

CREATE INDEX IF NOT EXISTS idx_ai_dec_blocked_recent
    ON ai_decisions_log(status, created_at DESC)
    WHERE status IN ('budget_blocked','loop_blocked');

-- ---------------------------------------------------------------------------
-- Vue dashboard : cout par projet / 24h
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_ai_cost_24h AS
SELECT
    project_id,
    COUNT(*) AS calls,
    SUM(cost_usd)::NUMERIC(12,6) AS total_cost_usd,
    SUM(tokens_in)::BIGINT AS tokens_in,
    SUM(tokens_out)::BIGINT AS tokens_out,
    SUM(CASE WHEN fallback_used THEN 1 ELSE 0 END)::INT AS fallbacks,
    SUM(CASE WHEN loop_detected THEN 1 ELSE 0 END)::INT AS loops,
    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END)::INT AS errors
FROM ai_decisions_log
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY project_id;

-- ---------------------------------------------------------------------------
-- Seal V9 Phase 9D
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

    seal_payload := '{"event":"v9_phase9d_ai_orchestrator","version":"9.0.0-phase9d","date":"2026-04-30","tables":["ai_decisions_log"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_040_v9_ai_orchestrator',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9D ai_orchestrator sealed (chain_hash=%)', new_chain_hash;
END
$$;
