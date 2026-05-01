-- 041 : V9 Phase 9C — Intelligence Engine (qualifications + pricings + assemblies + progression)
-- 2026-04-30
--
-- Le master plan reservait 041 a 'pricing_history' uniquement, mais Phase 9C
-- englobe aussi qualifications/assemblies/progression. On consolide en une
-- seule migration coherente, voir ADR-11.
--
-- Tables :
--   intelligence_qualifications : 1 ligne par CDC analyse
--   intelligence_pricings       : 1 ligne par devis emis
--   intelligence_assemblies     : 1 ligne par assemblage qualification + pricing + pack
--   project_progression         : 6 lignes par projet (1 par phase)

-- ---------------------------------------------------------------------------
-- 1) intelligence_qualifications
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_qualifications (
    id                  BIGSERIAL PRIMARY KEY,
    qualification_id    UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    pack_hint           TEXT NOT NULL,
    facets_json         JSONB NOT NULL,
    detected_domain     TEXT NOT NULL,
    detected_locales    TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    risks               TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    confidence          TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    rationale           TEXT NOT NULL,
    cdc_text_hash       TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_iq_project_recent
    ON intelligence_qualifications(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_iq_pack_hint
    ON intelligence_qualifications(pack_hint, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_iq_low_confidence
    ON intelligence_qualifications(created_at DESC)
    WHERE confidence = 'low';

CREATE INDEX IF NOT EXISTS idx_iq_cdc_hash
    ON intelligence_qualifications(cdc_text_hash);

-- ---------------------------------------------------------------------------
-- 2) intelligence_pricings (= "pricing_history" du master plan)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_pricings (
    id                BIGSERIAL PRIMARY KEY,
    pricing_id        UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id        TEXT NOT NULL,
    pack_id           TEXT NOT NULL,
    status            TEXT NOT NULL CHECK (status IN ('ok','requires_manual_quote')),
    currency          TEXT NOT NULL,
    net_price         NUMERIC(12,2) NOT NULL DEFAULT 0,
    tax_amount        NUMERIC(12,2) NOT NULL DEFAULT 0,
    gross_price       NUMERIC(12,2) NOT NULL DEFAULT 0,
    facets_json       JSONB NOT NULL DEFAULT '{}'::jsonb,
    coefficients_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    breakdown_json    JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json        JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ip_project_recent
    ON intelligence_pricings(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ip_status
    ON intelligence_pricings(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ip_pack
    ON intelligence_pricings(pack_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 3) intelligence_assemblies
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS intelligence_assemblies (
    id                  BIGSERIAL PRIMARY KEY,
    assembly_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id          TEXT NOT NULL,
    qualification_id    UUID NOT NULL REFERENCES intelligence_qualifications(qualification_id),
    pricing_id          UUID REFERENCES intelligence_pricings(pricing_id),
    pack_id             TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('auto','manual_quote','degraded')),
    modules             TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    deliverables        TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    selected_addons     TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    phase_weights_json  JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes_json          JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ia_project_recent
    ON intelligence_assemblies(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ia_outcome
    ON intelligence_assemblies(outcome, created_at DESC);

-- ---------------------------------------------------------------------------
-- 4) project_progression : 6 lignes par projet (1 par phase)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_progression (
    id                    BIGSERIAL PRIMARY KEY,
    project_id            TEXT NOT NULL,
    phase                 TEXT NOT NULL CHECK (phase IN
                              ('ANALYSIS','DESIGN','CORE','FEATURES','TESTING','DEPLOY')),
    weight_pct            INTEGER NOT NULL CHECK (weight_pct BETWEEN 1 AND 60),
    status                TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending','in_progress','done')),
    completion_pct        INTEGER NOT NULL DEFAULT 0
                              CHECK (completion_pct BETWEEN 0 AND 100),
    started_at            TIMESTAMPTZ,
    completed_at          TIMESTAMPTZ,
    paywall_triggered_at  TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, phase)
);

CREATE INDEX IF NOT EXISTS idx_pp_project_phase
    ON project_progression(project_id, phase);

CREATE INDEX IF NOT EXISTS idx_pp_in_progress
    ON project_progression(updated_at DESC)
    WHERE status = 'in_progress';

CREATE INDEX IF NOT EXISTS idx_pp_paywall
    ON project_progression(paywall_triggered_at DESC)
    WHERE paywall_triggered_at IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5) Seal V9 Phase 9C dans evidence_ledger
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

    seal_payload := '{"event":"v9_phase9c_intelligence_engine","version":"9.0.0-phase9c","date":"2026-04-30","tables":["intelligence_qualifications","intelligence_pricings","intelligence_assemblies","project_progression"]}';

    new_payload_hash := encode(digest(seal_payload, 'sha256'), 'hex');
    new_chain_hash   := encode(digest(last_chain_hash || new_payload_hash, 'sha256'), 'hex');

    INSERT INTO evidence_ledger (actor, kind, payload_hash, prev_hash, chain_hash, payload_json)
    VALUES (
        'migration_041_v9_intelligence',
        'feature',
        new_payload_hash,
        last_chain_hash,
        new_chain_hash,
        seal_payload::jsonb
    );

    RAISE NOTICE 'V9 Phase 9C intelligence engine sealed (chain_hash=%)', new_chain_hash;
END
$$;
