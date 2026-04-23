-- ============================================================
-- 024_ctc_phase_gates.sql - V5.3 BLOC 11
-- 5 gates nommes + journal des tentatives de passage
-- ============================================================

CREATE TABLE IF NOT EXISTS phase_gates (
    gate_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id UUID REFERENCES tasks(id) ON DELETE SET NULL,
    phase_from VARCHAR(30) NOT NULL,
    phase_to VARCHAR(30) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','open','closed','rework')),
    validation_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_chain_ref UUID REFERENCES evidence_chain_events(event_id),
    actor VARCHAR(120) NOT NULL,
    opened_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_phase_gates_task
    ON phase_gates(task_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_phase_gates_status
    ON phase_gates(status, created_at DESC);

-- Journal des echecs de passage (append-only)
CREATE TABLE IF NOT EXISTS phase_gate_failures (
    id BIGSERIAL PRIMARY KEY,
    gate_id UUID REFERENCES phase_gates(gate_id) ON DELETE CASCADE,
    reason_code VARCHAR(40) NOT NULL,
    reason_text TEXT NOT NULL,
    layers_failed JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Definition des 5 gates (statique pour introspection)
CREATE TABLE IF NOT EXISTS phase_gate_definitions (
    name VARCHAR(40) PRIMARY KEY,
    phase_from VARCHAR(30) NOT NULL,
    phase_to VARCHAR(30) NOT NULL,
    conditions JSONB NOT NULL,
    description TEXT
);

INSERT INTO phase_gate_definitions(name, phase_from, phase_to, conditions, description)
VALUES
  ('design_to_build', 'design', 'build',
   '{"rules":["no_open_ambiguity","specs_validated","requirements_proven"]}'::jsonb,
   'Toute ambiguite critique ouverte doit etre tracee'),
  ('build_to_validate', 'build', 'validate',
   '{"rules":["evidence_chain_bound","unit_tests_pass","sbom_generated"]}'::jsonb,
   'Artefacts lies a chaine evidence, tests unitaires OK'),
  ('validate_to_release', 'validate', 'release',
   '{"rules":["no_critical_contradictions","sources_fresh","7_layers_pass","all_dims_above_threshold"]}'::jsonb,
   '7 couches PASS + toutes dimensions >= seuil'),
  ('release_to_operate', 'release', 'operate',
   '{"rules":["security_proven","compliance_proven","prod_readiness_proven","chain_integrity"]}'::jsonb,
   'Securite + conformite + prod-readiness prouvees'),
  ('operate_to_rework', 'operate', 'rework',
   '{"rules":["anomaly_detected","evidence_stale","external_change","drift_detected"]}'::jsonb,
   'Anomalie/drift/changement externe declenchent rework')
ON CONFLICT (name) DO NOTHING;
