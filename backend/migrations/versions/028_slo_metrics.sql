-- ============================================================
-- 028_slo_metrics.sql - V5.7 SLO/SLI tracking (fiabilite 99.8%)
-- ============================================================

CREATE TABLE IF NOT EXISTS slo_definitions (
    slo_name VARCHAR(80) PRIMARY KEY,
    description TEXT,
    target_percent DECIMAL(5,3) NOT NULL
        CHECK (target_percent > 0 AND target_percent < 100),
    window_days INTEGER NOT NULL DEFAULT 30,
    sli_type VARCHAR(40) NOT NULL
        CHECK (sli_type IN ('availability','latency','error_rate','freshness')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO slo_definitions(slo_name, description, target_percent, sli_type, window_days)
VALUES
  ('availability',       'Uptime global 30j',              99.800, 'availability', 30),
  ('latency_p99',        'Latence p99 HTTP < 500ms',       99.000, 'latency',      7),
  ('error_rate',         'Taux erreur 5xx < 0.2%',         99.800, 'error_rate',   7),
  ('backup_freshness',   'Dernier backup < 2h age',        99.500, 'freshness',   30)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS slo_measurements (
    id BIGSERIAL PRIMARY KEY,
    slo_name VARCHAR(80) NOT NULL REFERENCES slo_definitions(slo_name),
    measured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    good_count BIGINT NOT NULL DEFAULT 0,
    bad_count BIGINT NOT NULL DEFAULT 0,
    total_count BIGINT GENERATED ALWAYS AS (good_count + bad_count) STORED,
    sli_value DECIMAL(8,5),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_slo_meas_name_ts
    ON slo_measurements(slo_name, measured_at DESC);

CREATE TABLE IF NOT EXISTS slo_incidents (
    id BIGSERIAL PRIMARY KEY,
    slo_name VARCHAR(80) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    severity VARCHAR(20) NOT NULL DEFAULT 'warning'
        CHECK (severity IN ('info','warning','critical')),
    burn_rate DECIMAL(6,2),
    reason TEXT,
    resolved_auto BOOLEAN NOT NULL DEFAULT FALSE,
    resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_slo_incidents_slo
    ON slo_incidents(slo_name, started_at DESC);

-- Seed nouveau schedule V5.7 pour task_backup_hourly (backup incremental)
INSERT INTO workflow_schedules(task_name, cron_expression, tier, description)
VALUES
  ('task_backup_hourly', 'every hour at :15', 7, 'Backup incremental 24 derniers')
ON CONFLICT (task_name) DO UPDATE SET
  cron_expression = EXCLUDED.cron_expression,
  tier = EXCLUDED.tier,
  description = EXCLUDED.description;
