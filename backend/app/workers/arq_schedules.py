"""V5.5 Automation - WorkerSettings arq pour les 26 cron jobs.

Entree d'execution : `arq app.workers.arq_schedules.WorkerSettings`.

Chaque cron correspond a une ligne seedee dans `workflow_schedules`
(migration 026). Les expressions sont traduites en kwargs `arq.cron`.
"""
from __future__ import annotations

from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.config import get_settings
from app.workers._runtime import automation_shutdown, automation_startup
from app.workers.event_workflows import (
    EVENT_TASKS,
    task_dead_letter_processor,
)
from app.workers.tasks import (
    ALL_TASKS,
    task_agent_performance_report,
    task_autonomy_chaos,
    task_backup_database,
    task_backup_hourly,
    task_benchmarks_run,
    task_browser_contract_verify,
    task_cost_report_generation,
    task_coverage_report,
    task_cve_poll,
    task_dependencies_audit,
    task_drift_detection,
    task_evidence_chain_verification,
    task_failure_archetype_mining,
    task_health_deep_check,
    task_innovation_scout,
    task_memory_consolidation,
    task_meta_optimizer,
    task_nightly_optimizer,
    task_prompt_variants_rebalance,
    task_queue_saturation_monitor,
    task_regulatory_dz_poll,
    task_rework_convergence_audit,
    task_sbom_regeneration,
    task_security_scan,
    task_tenant_isolation_audit,
    task_truth_integrity_check,
    task_vault_rotation_check,
)

_settings = get_settings()


# ---------------------------------------------------------------- cron builders
# arq.cron accepts iterable `minute`, `hour`, ... (set of values) or None (all).

def _every_n_minutes(n: int) -> set[int]:
    return set(range(0, 60, n))


CRON_JOBS: list[Any] = [
    # ============ TIER 1 - Critique (10-30 min) ============
    cron(task_queue_saturation_monitor, name="task_queue_saturation_monitor",
         minute=_every_n_minutes(15), max_tries=3, keep_result=3600),
    cron(task_health_deep_check, name="task_health_deep_check",
         minute=_every_n_minutes(10), max_tries=3, keep_result=3600),
    cron(task_truth_integrity_check, name="task_truth_integrity_check",
         minute=_every_n_minutes(30), max_tries=3, keep_result=3600),
    cron(task_evidence_chain_verification, name="task_evidence_chain_verification",
         minute=_every_n_minutes(30), second=30, max_tries=3, keep_result=3600),

    # ============ TIER 2 - Security (2-4x/day) ============
    cron(task_vault_rotation_check, name="task_vault_rotation_check",
         hour={8, 14, 20}, minute=0, max_tries=3, keep_result=3600),
    cron(task_tenant_isolation_audit, name="task_tenant_isolation_audit",
         hour={9, 17}, minute=0, max_tries=3, keep_result=3600),
    cron(task_security_scan, name="task_security_scan",
         hour={6}, minute=0, max_tries=3, keep_result=3600),
    cron(task_cve_poll, name="task_cve_poll",
         hour={0, 6, 12, 18}, minute=0, max_tries=3, keep_result=3600),
    cron(task_sbom_regeneration, name="task_sbom_regeneration",
         hour={2}, minute=30, max_tries=3, keep_result=3600),
    cron(task_dependencies_audit, name="task_dependencies_audit",
         hour={3}, minute=0, max_tries=3, keep_result=3600),

    # ============ TIER 3 - Optimisation (nocturne) ============
    cron(task_nightly_optimizer, name="task_nightly_optimizer",
         hour={1}, minute=0, max_tries=3, keep_result=3600),
    cron(task_meta_optimizer, name="task_meta_optimizer",
         hour={2}, minute=0, max_tries=3, keep_result=3600),
    cron(task_innovation_scout, name="task_innovation_scout",
         hour={3}, minute=30, max_tries=3, keep_result=3600),
    cron(task_autonomy_chaos, name="task_autonomy_chaos",
         hour={2}, minute=30, max_tries=3, keep_result=3600),
    cron(task_drift_detection, name="task_drift_detection",
         hour={4}, minute=0, max_tries=3, keep_result=3600),
    cron(task_failure_archetype_mining, name="task_failure_archetype_mining",
         hour={4}, minute=30, max_tries=3, keep_result=3600),
    cron(task_rework_convergence_audit, name="task_rework_convergence_audit",
         hour={5}, minute=0, max_tries=3, keep_result=3600),

    # ============ TIER 4 - Memoire (nocturne) ============
    cron(task_memory_consolidation, name="task_memory_consolidation",
         hour={3}, minute=0, max_tries=3, keep_result=3600),
    cron(task_prompt_variants_rebalance, name="task_prompt_variants_rebalance",
         hour={4}, minute=0, max_tries=3, keep_result=3600),
    cron(task_benchmarks_run, name="task_benchmarks_run",
         hour={5}, minute=30, max_tries=3, keep_result=3600),

    # ============ TIER 5 - Business Intelligence (matin) ============
    cron(task_cost_report_generation, name="task_cost_report_generation",
         hour={7}, minute=0, max_tries=3, keep_result=3600),
    cron(task_agent_performance_report, name="task_agent_performance_report",
         hour={7}, minute=30, max_tries=3, keep_result=3600),
    cron(task_coverage_report, name="task_coverage_report",
         hour={8}, minute=0, max_tries=3, keep_result=3600),

    # ============ TIER 6 - Veille ============
    cron(task_regulatory_dz_poll, name="task_regulatory_dz_poll",
         hour={9, 15}, minute=0, max_tries=3, keep_result=3600),
    cron(task_browser_contract_verify, name="task_browser_contract_verify",
         hour={6}, minute=30, max_tries=3, keep_result=3600),

    # ============ TIER 7 - Backup (2x/jour + horaire incremental) ============
    cron(task_backup_database, name="task_backup_database",
         hour={0, 12}, minute=30, max_tries=3, keep_result=3600),
    cron(task_backup_hourly, name="task_backup_hourly",
         minute=15, max_tries=2, keep_result=3600),

    # ============ DLQ processor (horaire) ============
    cron(task_dead_letter_processor, name="task_dead_letter_processor",
         minute=5, max_tries=2, keep_result=3600),
]

assert len(CRON_JOBS) == 28, (
    f"Expected 27 cron tasks + 1 DLQ processor, got {len(CRON_JOBS)}"
)


_FUNCTIONS: list[Any] = ALL_TASKS + EVENT_TASKS + [task_dead_letter_processor]


class WorkerSettings:
    """Configuration Arq V5.5 automation."""
    functions: ClassVar[list[Any]] = _FUNCTIONS
    cron_jobs: ClassVar[list[Any]] = CRON_JOBS
    on_startup = automation_startup
    on_shutdown = automation_shutdown
    redis_settings = RedisSettings(
        host=_settings.REDIS_HOST,
        port=_settings.REDIS_PORT,
        password=_settings.REDIS_PASSWORD or None,
        database=_settings.REDIS_DB,
    )
    max_jobs = 20
    job_timeout = 900
    keep_result = 3600
    max_tries = 3
    # Exponential backoff : arq appelle job_retry entre les tentatives
    # default is 3-5s, bumped to 5s/25s/125s via retry_jobs=True.
    retry_jobs = True
