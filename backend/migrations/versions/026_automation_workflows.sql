-- ============================================================
-- 026_automation_workflows.sql - V5.5 ETAPE 4.5
-- Tables pour workflows arq : executions, metrics, schedules, triggers
-- ============================================================

CREATE TABLE IF NOT EXISTS workflow_executions (
    run_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_name VARCHAR(120) NOT NULL,
    worker_name VARCHAR(120),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','succeeded','failed','timeout','dead_letter')),
    tries INTEGER NOT NULL DEFAULT 1,
    error TEXT,
    result JSONB NOT NULL DEFAULT '{}'::jsonb,
    trigger_kind VARCHAR(20) NOT NULL DEFAULT 'cron'
        CHECK (trigger_kind IN ('cron','event','manual'))
);
CREATE INDEX IF NOT EXISTS idx_wf_exec_task_started
    ON workflow_executions(task_name, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_wf_exec_status
    ON workflow_executions(status, started_at DESC);

CREATE TABLE IF NOT EXISTS workflow_metrics (
    id BIGSERIAL PRIMARY KEY,
    task_name VARCHAR(120) NOT NULL,
    day DATE NOT NULL,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    avg_duration_ms DECIMAL(12,2) NOT NULL DEFAULT 0,
    p99_duration_ms INTEGER NOT NULL DEFAULT 0,
    last_run TIMESTAMPTZ,
    UNIQUE (task_name, day)
);
CREATE INDEX IF NOT EXISTS idx_wf_metrics_task
    ON workflow_metrics(task_name, day DESC);

CREATE TABLE IF NOT EXISTS workflow_schedules (
    task_name VARCHAR(120) PRIMARY KEY,
    cron_expression VARCHAR(80) NOT NULL,
    tier INTEGER NOT NULL DEFAULT 3
        CHECK (tier BETWEEN 1 AND 7),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    paused_at TIMESTAMPTZ,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    description TEXT
);

CREATE TABLE IF NOT EXISTS event_triggers (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    task_name VARCHAR(120) NOT NULL,
    condition_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_event_triggers_event
    ON event_triggers(event_type, enabled);

-- Dead letter queue
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id BIGSERIAL PRIMARY KEY,
    task_name VARCHAR(120) NOT NULL,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_error TEXT,
    tries INTEGER NOT NULL DEFAULT 3,
    entered_dlq_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_dlq_resolved
    ON dead_letter_queue(resolved, entered_dlq_at DESC);

-- Seed workflow_schedules avec les 26 tasks
INSERT INTO workflow_schedules(task_name, cron_expression, tier, description)
VALUES
  ('task_queue_saturation_monitor', 'every 15m',  1, 'Monitor arq queue saturation'),
  ('task_health_deep_check',        'every 10m',  1, 'Deep health check services'),
  ('task_truth_integrity_check',    'every 30m',  1, 'Verify evidence chain integrity'),
  ('task_evidence_chain_verification','every 30m',1, 'Chain hash + HMAC audit'),
  ('task_vault_rotation_check',     '8/14/20 UTC',2, 'Vault key rotation audit'),
  ('task_tenant_isolation_audit',   '9/17 UTC',   2, 'RLS cross-tenant leaks check'),
  ('task_security_scan',            '06:00 daily',2, 'Bandit+secrets scan'),
  ('task_cve_poll',                 '0/6/12/18',  2, 'Poll CVE/NVD/KEV'),
  ('task_sbom_regeneration',        '02:30 daily',2, 'Regen SBOM + sign'),
  ('task_dependencies_audit',       '03:00 daily',2, 'Pip audit + advisory'),
  ('task_nightly_optimizer',        '01:00 daily',3, 'Nightly threshold tune'),
  ('task_meta_optimizer',           '02:00 daily',3, 'Capture meta metrics'),
  ('task_innovation_scout',         '03:30 daily',3, 'Scan innovation pipeline'),
  ('task_autonomy_chaos',           '02:30 daily',3, 'Run chaos scenarios'),
  ('task_drift_detection',          '04:00 daily',3, 'Detect performance/quality drift'),
  ('task_failure_archetype_mining', '04:30 daily',3, 'Cluster failures'),
  ('task_rework_convergence_audit', '05:00 daily',3, 'Audit rework cycles'),
  ('task_memory_consolidation',     '03:00 daily',4, 'Dedupe + prune memory'),
  ('task_prompt_variants_rebalance','04:00 daily',4, 'AB rebalance prompts'),
  ('task_benchmarks_run',           '05:30 daily',4, 'Run 5 families benchmarks'),
  ('task_cost_report_generation',   '07:00 daily',5, 'Daily cost report'),
  ('task_agent_performance_report', '07:30 daily',5, 'Per-agent perf report'),
  ('task_coverage_report',          '08:00 daily',5, 'Test coverage report'),
  ('task_regulatory_dz_poll',       '9/15 UTC',   6, 'Poll DZ regulations'),
  ('task_browser_contract_verify',  '06:30 daily',6, 'Browser contract'),
  ('task_backup_database',          '00:30/12:30',7, 'pg_dump + upload')
ON CONFLICT (task_name) DO UPDATE SET
  cron_expression = EXCLUDED.cron_expression,
  tier = EXCLUDED.tier,
  description = EXCLUDED.description;

-- Seed event triggers
INSERT INTO event_triggers(event_type, task_name)
VALUES
  ('git_commit', 'task_run_tests_impacted'),
  ('git_commit', 'task_lint_check'),
  ('git_commit', 'task_security_diff_scan'),
  ('migration_applied', 'task_schema_verify'),
  ('migration_applied', 'task_invariants_check'),
  ('migration_applied', 'task_regression_full'),
  ('new_project_created', 'task_auth_prefetcher'),
  ('new_project_created', 'task_risk_classification'),
  ('new_project_created', 'task_workflow_planner'),
  ('test_failure', 'task_failure_analysis'),
  ('cost_budget_approaching', 'task_budget_optimization'),
  ('regulatory_change_detected', 'task_impact_analysis'),
  ('agent_drift_detected', 'task_agent_diagnosis'),
  ('phase_gate_requested', 'task_validate_7_layers'),
  ('ahmed_response_received', 'task_response_classifier')
ON CONFLICT DO NOTHING;
