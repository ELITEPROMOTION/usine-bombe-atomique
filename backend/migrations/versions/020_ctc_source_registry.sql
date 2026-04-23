-- ============================================================
-- 020_ctc_source_registry.sql - V5.3 BLOC 1
-- Registre versionne des sources de verite
-- ============================================================

CREATE TABLE IF NOT EXISTS truth_sources (
    source_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    domain VARCHAR(60) NOT NULL,        -- web_standards|security|compliance_dz|...
    url TEXT NOT NULL UNIQUE,
    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN ('api','documentation','specification',
                                'database','government','academic')),
    authority_tier INTEGER NOT NULL
        CHECK (authority_tier BETWEEN 1 AND 5),
    access_mode VARCHAR(40) NOT NULL
        CHECK (access_mode IN ('api_native','sdk_official','cli_official',
                                'connector_orchestrator','agentic_navigation',
                                'desktop_automation','manual')),
    freshness_policy_seconds INTEGER NOT NULL DEFAULT 86400,
    refresh_frequency VARCHAR(20) NOT NULL DEFAULT 'daily',
    checksum CHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','quarantined','deprecated')),
    last_validated_at TIMESTAMPTZ,
    access_justification TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_truth_sources_domain
    ON truth_sources(domain, authority_tier);
CREATE INDEX IF NOT EXISTS idx_truth_sources_status
    ON truth_sources(status);

-- Log fetch/harvest cycles
CREATE TABLE IF NOT EXISTS evidence_harvesting_log (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE CASCADE,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    http_status INTEGER,
    bytes_received INTEGER NOT NULL DEFAULT 0,
    content_hash CHAR(64),
    changed BOOLEAN NOT NULL DEFAULT FALSE,
    error TEXT,
    latency_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_harvest_log_source
    ON evidence_harvesting_log(source_id, fetched_at DESC);

-- Circuit breaker events
CREATE TABLE IF NOT EXISTS circuit_breaker_events (
    id BIGSERIAL PRIMARY KEY,
    source_id UUID REFERENCES truth_sources(source_id) ON DELETE CASCADE,
    event_type VARCHAR(30) NOT NULL
        CHECK (event_type IN ('opened','half_open','closed','quarantined','restored')),
    reason TEXT,
    failures_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed quelques sources Tier 1-2 mondiales
INSERT INTO truth_sources(domain, url, source_type, authority_tier,
    access_mode, freshness_policy_seconds, refresh_frequency, notes)
VALUES
  ('web_standards', 'https://developer.mozilla.org/en-US/docs/Web',
    'documentation', 3, 'agentic_navigation', 86400, 'daily',
    'MDN Tier 3 (agregateur repute)'),
  ('web_standards', 'https://www.w3.org/standards/',
    'specification', 1, 'agentic_navigation', 604800, 'weekly',
    'W3C Tier 1 (standards)'),
  ('security', 'https://cve.mitre.org/',
    'database', 1, 'api_native', 900, '15min',
    'CVE MITRE Tier 1'),
  ('security', 'https://nvd.nist.gov/',
    'database', 1, 'api_native', 900, '15min',
    'NVD NIST Tier 1'),
  ('security', 'https://www.cisa.gov/known-exploited-vulnerabilities-catalog',
    'government', 1, 'api_native', 900, '15min',
    'CISA KEV Tier 1'),
  ('security', 'https://osv.dev/',
    'database', 2, 'api_native', 900, '15min',
    'OSV Tier 2 (Google)'),
  ('security', 'https://owasp.org/',
    'documentation', 1, 'agentic_navigation', 86400, 'daily',
    'OWASP Tier 1'),
  ('lang_python', 'https://docs.python.org/3/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'Python.org docs Tier 2'),
  ('framework', 'https://fastapi.tiangolo.com/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'FastAPI docs Tier 2'),
  ('database', 'https://www.postgresql.org/docs/',
    'documentation', 2, 'agentic_navigation', 86400, 'daily',
    'PostgreSQL docs Tier 2'),
  ('compliance_dz', 'https://www.joradp.dz/',
    'government', 1, 'manual', 604800, 'weekly',
    'Journal Officiel DZ Tier 1'),
  ('compliance_eu', 'https://eur-lex.europa.eu/',
    'government', 1, 'agentic_navigation', 604800, 'weekly',
    'EUR-Lex Tier 1')
ON CONFLICT (url) DO NOTHING;
