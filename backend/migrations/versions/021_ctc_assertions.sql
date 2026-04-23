-- ============================================================
-- 021_ctc_assertions.sql - V5.3 BLOC 3
-- truth_assertions : assertions atomiques typees
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_assertions (
    assertion_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE SET NULL,
    source_version VARCHAR(80),
    extracted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    content_hash CHAR(64) NOT NULL,
    normalized_text TEXT NOT NULL,
    assertion_type VARCHAR(20) NOT NULL
        CHECK (assertion_type IN (
            'fact','rule','constraint','warning','vulnerability',
            'deprecation','assumption','contradiction','benchmark','requirement')),
    domain VARCHAR(60) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('info','low','medium','high','critical')),
    confidence INTEGER NOT NULL DEFAULT 80
        CHECK (confidence BETWEEN 0 AND 100),
    freshness_score INTEGER NOT NULL DEFAULT 100
        CHECK (freshness_score BETWEEN 0 AND 100),
    status VARCHAR(20) NOT NULL DEFAULT 'unproven'
        CHECK (status IN ('proven','probable','unproven','conflicting','stale','blocked'))
);
CREATE INDEX IF NOT EXISTS idx_assertions_domain
    ON truth_assertions(domain, status);
CREATE INDEX IF NOT EXISTS idx_assertions_hash
    ON truth_assertions(content_hash);
CREATE INDEX IF NOT EXISTS idx_assertions_severity
    ON truth_assertions(severity, confidence DESC);

-- Conflits detectes entre sources
CREATE TABLE IF NOT EXISTS truth_conflicts (
    conflict_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assertion_a UUID REFERENCES truth_assertions(assertion_id),
    assertion_b UUID REFERENCES truth_assertions(assertion_id),
    conflict_kind VARCHAR(30) NOT NULL
        CHECK (conflict_kind IN ('version_mismatch','scope_difference',
                                  'interpretation_difference','error','unknown')),
    resolution VARCHAR(30),
    resolution_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);
