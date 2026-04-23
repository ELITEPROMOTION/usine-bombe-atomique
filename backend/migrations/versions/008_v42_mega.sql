-- ============================================================
-- 008_v42_mega.sql - V4.2 : 9 nouvelles tables pour 24 upgrades
-- ============================================================

-- 35 : Defect Taxonomy
CREATE TABLE IF NOT EXISTS defect_taxonomy (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    nature VARCHAR(30) NOT NULL
        CHECK (nature IN ('structure','logique','securite','conformite','performance')),
    gravite VARCHAR(20) NOT NULL
        CHECK (gravite IN ('info','mineure','bloquante','vitale')),
    rayon_impact VARCHAR(20) NOT NULL DEFAULT 'local'
        CHECK (rayon_impact IN ('local','module','service','system')),
    recurrence INTEGER NOT NULL DEFAULT 1,
    signature VARCHAR(64) NOT NULL,
    title VARCHAR(240) NOT NULL,
    details TEXT,
    correction_patch_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (task_id, signature)
);
CREATE INDEX IF NOT EXISTS idx_defect_nature ON defect_taxonomy(nature, gravite);
CREATE INDEX IF NOT EXISTS idx_defect_task   ON defect_taxonomy(task_id);

-- 30 : Regles DZ parametrables en base (versionnees)
CREATE TABLE IF NOT EXISTS dz_rules_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    rule_code VARCHAR(40) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    label VARCHAR(240) NOT NULL,
    regex_positive TEXT,
    regex_negative TEXT,
    threshold_min DECIMAL(10,6),
    threshold_max DECIMAL(10,6),
    severity VARCHAR(10) NOT NULL DEFAULT 'medium'
        CHECK (severity IN ('low','medium','high','critical')),
    created_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (rule_code, version)
);

INSERT INTO dz_rules_config (rule_code, version, label, regex_positive, threshold_min, threshold_max, severity) VALUES
  ('R1_TVA19',   1, 'TVA 19% mentionnee + constante',      '\bTVA\b.*0\.19|\b19\s*%',      0.19, 0.19, 'high'),
  ('R2_TAP2',    1, 'TAP 2% mentionnee + constante',       '\bTAP\b.*0\.02|\b2\s*%',       0.02, 0.02, 'high'),
  ('R3_CNAS',    1, 'CNAS 9% salarie + 26% employeur',     '\b0\.09\b.*\b0\.26\b',          0.09, 0.26, 'high'),
  ('R4_IRG',     1, 'IRG progressif 4 tranches',           'IRG',                            NULL, NULL, 'high'),
  ('R5_NIN18',   1, 'NIN 18 chiffres',                      '\bnin\b.*\b18\b',                 18.0, 18.0, 'medium'),
  ('R6_DZD',     1, 'Devise DZD / Dinar',                  '\bDZD\b|\bDinar',                NULL, NULL, 'medium'),
  ('R7_NoForeignRegs', 1, 'Pas de regs non-DZ exclusives', NULL,                              NULL, NULL, 'critical'),
  ('R8_VEFA_Paliers', 1, 'Paliers VEFA 20/15/35/25/5',     '20.*15.*35.*25.*5',               NULL, NULL, 'high')
ON CONFLICT (rule_code, version) DO NOTHING;

-- 37 : Pipeline innovation
CREATE TABLE IF NOT EXISTS innovation_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    kind VARCHAR(30) NOT NULL
        CHECK (kind IN ('model','library','tool','strategy')),
    name VARCHAR(200) NOT NULL,
    summary TEXT NOT NULL,
    stage VARCHAR(30) NOT NULL DEFAULT 'scout'
        CHECK (stage IN ('scout','qualification','benchmark',
                          'risk_review','pending_approval',
                          'staged','active','rollback','rejected')),
    benchmark_score DECIMAL(5,3),
    risk_notes TEXT,
    approved_by VARCHAR(120),
    approved_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kind, name)
);

-- 24 : Cache semantique (embedding stocke en JSONB si pgvector absent)
CREATE TABLE IF NOT EXISTS semantic_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    spec_hash CHAR(64) NOT NULL UNIQUE,
    spec_excerpt TEXT NOT NULL,
    fingerprint JSONB NOT NULL,     -- representation numerique simple (fallback pgvector)
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    artifact_count INTEGER NOT NULL DEFAULT 0,
    reuse_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_hit_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_semcache_last ON semantic_cache(last_hit_at DESC);

-- 28 : DAG checkpoints (miroir Redis pour le cas crash - persistant)
CREATE TABLE IF NOT EXISTS dag_checkpoints (
    task_id UUID PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
    completed_waves JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_wave_index INTEGER NOT NULL DEFAULT -1,
    agent_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 36 : Truth KPI snapshots (aggregation periodique)
CREATE TABLE IF NOT EXISTS truth_kpi_snapshots (
    id BIGSERIAL PRIMARY KEY,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    defect_escape_rate DECIMAL(6,4),
    false_pass_rate DECIMAL(6,4),
    false_fail_rate DECIMAL(6,4),
    confidence_calibration_error DECIMAL(6,4),
    revalidation_completeness_rate DECIMAL(6,4),
    patch_recurrence_rate DECIMAL(6,4),
    runtime_contradiction_rate DECIMAL(6,4),
    proof_coverage_rate DECIMAL(6,4),
    samples INTEGER NOT NULL DEFAULT 0
);

-- 29 : Journal quorum judge
CREATE TABLE IF NOT EXISTS quorum_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    judge_1_verdict VARCHAR(20) NOT NULL,
    judge_2_verdict VARCHAR(20) NOT NULL,
    judge_3_verdict VARCHAR(20) NOT NULL,
    final_verdict VARCHAR(20) NOT NULL,
    has_disagreement BOOLEAN NOT NULL DEFAULT FALSE,
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_quorum_disagree ON quorum_decisions(has_disagreement);

-- 14 : Rollback automatique
CREATE TABLE IF NOT EXISTS rollback_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    trigger_reason VARCHAR(60) NOT NULL,
    confidence_before DECIMAL(6,4),
    confidence_after DECIMAL(6,4),
    artifact_version_before VARCHAR(64),
    artifact_version_after VARCHAR(64),
    auto_triggered BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 23 : Audit reseau sandbox
CREATE TABLE IF NOT EXISTS network_audit_log (
    id BIGSERIAL PRIMARY KEY,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    sandbox_id VARCHAR(80) NOT NULL,
    outbound_attempts INTEGER NOT NULL DEFAULT 0,
    violations_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    verdict VARCHAR(20) NOT NULL DEFAULT 'clean'
        CHECK (verdict IN ('clean','violated','inconclusive')),
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
