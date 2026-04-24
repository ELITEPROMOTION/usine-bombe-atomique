-- ============================================================
-- 027_feature_flags.sql - V5.6 Universalite
-- Feature flags production-grade (hierarchie user > tenant > % rollout > global)
-- ============================================================

CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name VARCHAR(120) PRIMARY KEY,
    description TEXT,
    enabled_globally BOOLEAN NOT NULL DEFAULT FALSE,
    enabled_tenants UUID[] NOT NULL DEFAULT '{}'::uuid[],
    enabled_users UUID[] NOT NULL DEFAULT '{}'::uuid[],
    rollout_percent INTEGER NOT NULL DEFAULT 0
        CHECK (rollout_percent BETWEEN 0 AND 100),
    condition_cel TEXT,
    auto_disable_on_error BOOLEAN NOT NULL DEFAULT FALSE,
    error_threshold_percent INTEGER NOT NULL DEFAULT 10
        CHECK (error_threshold_percent BETWEEN 1 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(200)
);
CREATE INDEX IF NOT EXISTS idx_feature_flags_globally
    ON feature_flags(enabled_globally) WHERE enabled_globally = TRUE;

CREATE TABLE IF NOT EXISTS feature_flag_events (
    id BIGSERIAL PRIMARY KEY,
    flag_name VARCHAR(120) NOT NULL,
    event_type VARCHAR(40) NOT NULL
        CHECK (event_type IN ('evaluated','error','toggle','rollout_changed')),
    tenant_id UUID,
    user_id UUID,
    result BOOLEAN,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ff_events_flag
    ON feature_flag_events(flag_name, created_at DESC);

-- Seed 5 flags de demo (1 par domaine)
INSERT INTO feature_flags(flag_name, description, enabled_globally)
VALUES
  ('domain.fiscal_dz.enabled',    'Active le domaine fiscal DZ',    TRUE),
  ('domain.juridique.enabled',    'Active le domaine juridique',    TRUE),
  ('domain.logistique.enabled',   'Active le domaine logistique',   TRUE),
  ('domain.rh.enabled',           'Active le domaine RH',           TRUE),
  ('domain.comptabilite.enabled', 'Active le domaine comptabilite', TRUE),
  ('feature.rules_hot_reload',    'Rechargement auto des rules YAML (<5s)', FALSE),
  ('feature.dark_mode',           'UI dark mode default',            TRUE)
ON CONFLICT (flag_name) DO NOTHING;
