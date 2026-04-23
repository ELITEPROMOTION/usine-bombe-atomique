-- ============================================================
-- 015_system_parameters.sql - V5.2 BLOC 2
-- Table system_parameters : regles PARAMETRIZABLE / LEARNABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS system_parameters (
    id BIGSERIAL PRIMARY KEY,
    parameter_key VARCHAR(120) NOT NULL,
    parameter_value JSONB NOT NULL,
    parameter_category VARCHAR(20) NOT NULL
        CHECK (parameter_category IN ('PARAMETRIZABLE','LEARNABLE')),
    allowed_min DECIMAL(18,6),
    allowed_max DECIMAL(18,6),
    requires_approval BOOLEAN NOT NULL DEFAULT FALSE,
    version INTEGER NOT NULL DEFAULT 1,
    changed_by VARCHAR(120) NOT NULL DEFAULT 'system',
    changed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    justification TEXT,
    rollback_value JSONB,
    UNIQUE (parameter_key, version)
);
CREATE INDEX IF NOT EXISTS idx_system_params_key
    ON system_parameters(parameter_key, version DESC);

-- Vue pratique : derniere version active par cle
CREATE OR REPLACE VIEW system_parameters_current AS
SELECT DISTINCT ON (parameter_key)
    parameter_key, parameter_value, parameter_category,
    allowed_min, allowed_max, requires_approval,
    version, changed_by, changed_at, justification
FROM system_parameters
ORDER BY parameter_key, version DESC;

-- Seed PARAMETRIZABLE
INSERT INTO system_parameters(parameter_key, parameter_value,
    parameter_category, requires_approval, justification)
VALUES
  ('confidence.threshold.critical_fiscal', '0.95'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'seuil confiance pour calcul fiscal DZ'),
  ('confidence.threshold.security', '0.90'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'seuil confiance securite'),
  ('confidence.threshold.ui_ux', '0.75'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'seuil UI/UX'),
  ('agent.timeout.default_seconds', '180'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'timeout par defaut agents'),
  ('budget.tokens.per_task', '60000'::jsonb,
   'PARAMETRIZABLE', FALSE,
   'budget tokens par tache'),
  ('rework.max_iterations', '3'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'max iterations rework'),
  ('lease.ttl.default_days', '30'::jsonb,
   'PARAMETRIZABLE', TRUE,
   'TTL lease par defaut')
ON CONFLICT (parameter_key, version) DO NOTHING;

-- Seed LEARNABLE avec bounds durs
INSERT INTO system_parameters(parameter_key, parameter_value,
    parameter_category, allowed_min, allowed_max, requires_approval,
    justification)
VALUES
  ('scoring.weight.correctness', '0.25'::jsonb,
   'LEARNABLE', 0.15, 0.40, FALSE,
   'poids correctness dans composite'),
  ('scoring.weight.quality', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.25, FALSE,
   'poids quality'),
  ('scoring.weight.coverage', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.25, FALSE,
   'poids coverage'),
  ('scoring.weight.security', '0.20'::jsonb,
   'LEARNABLE', 0.10, 0.35, FALSE,
   'poids security'),
  ('scoring.weight.conformity', '0.15'::jsonb,
   'LEARNABLE', 0.05, 0.30, FALSE,
   'poids conformity (DZ)'),
  ('scoring.weight.maintainability', '0.10'::jsonb,
   'LEARNABLE', 0.05, 0.20, FALSE,
   'poids maintainability'),
  ('pass_min', '0.80'::jsonb,
   'LEARNABLE', 0.75, 0.90, TRUE,
   'seuil pass_min'),
  ('cpass_min', '0.70'::jsonb,
   'LEARNABLE', 0.60, 0.80, TRUE,
   'seuil conditional pass_min'),
  ('soft_fail_min', '0.50'::jsonb,
   'LEARNABLE', 0.40, 0.70, TRUE,
   'seuil soft_fail_min')
ON CONFLICT (parameter_key, version) DO NOTHING;
