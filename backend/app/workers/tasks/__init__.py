"""V5.5 Automation - 26 tasks cron, organisees en 7 tiers.

Structure :
    tier1_critical     : monitoring (4 tasks, every 10-30 min)
    tier2_security     : security (6 tasks, 2-4 runs/day)
    tier3_optimization : nightly tune (7 tasks)
    tier4_memory       : memory/prompts/benchmarks (3 tasks)
    tier5_bi           : daily reports (3 tasks)
    tier6_veille       : regulatory + contracts (2 tasks)
    tier7_backup       : pg_dump (1 task)

Re-exports toutes les tasks + `ALL_TASKS` + `TASK_NAMES` pour compat
avec arq_schedules.py et event_workflows.py (imports existants preserves).
"""
from __future__ import annotations

from typing import Any

from . import (
    tier1_critical,
    tier2_security,
    tier3_optimization,
    tier4_memory,
    tier5_bi,
    tier6_veille,
    tier7_backup,
)
from .tier1_critical import (
    task_evidence_chain_verification,
    task_health_deep_check,
    task_queue_saturation_monitor,
    task_truth_integrity_check,
)
from .tier2_security import (
    task_cve_poll,
    task_dependencies_audit,
    task_sbom_regeneration,
    task_security_scan,
    task_tenant_isolation_audit,
    task_vault_rotation_check,
)
from .tier3_optimization import (
    task_autonomy_chaos,
    task_drift_detection,
    task_failure_archetype_mining,
    task_innovation_scout,
    task_meta_optimizer,
    task_nightly_optimizer,
    task_rework_convergence_audit,
)
from .tier4_memory import (
    task_benchmarks_run,
    task_memory_consolidation,
    task_prompt_variants_rebalance,
)
from .tier5_bi import (
    task_agent_performance_report,
    task_cost_report_generation,
    task_coverage_report,
)
from .tier6_veille import (
    task_browser_contract_verify,
    task_regulatory_dz_poll,
)
from .tier7_backup import (
    task_backup_database,
)

ALL_TASKS: list[Any] = (
    tier1_critical.ALL_TASKS
    + tier2_security.ALL_TASKS
    + tier3_optimization.ALL_TASKS
    + tier4_memory.ALL_TASKS
    + tier5_bi.ALL_TASKS
    + tier6_veille.ALL_TASKS
    + tier7_backup.ALL_TASKS
)

assert len(ALL_TASKS) == 26, f"Expected 26 tasks, got {len(ALL_TASKS)}"

TASK_NAMES: list[str] = [t.__automation_task__ for t in ALL_TASKS]  # type: ignore[attr-defined]

__all__ = [
    "ALL_TASKS",
    "TASK_NAMES",
    # Tier 1
    "task_queue_saturation_monitor",
    "task_health_deep_check",
    "task_truth_integrity_check",
    "task_evidence_chain_verification",
    # Tier 2
    "task_vault_rotation_check",
    "task_tenant_isolation_audit",
    "task_security_scan",
    "task_cve_poll",
    "task_sbom_regeneration",
    "task_dependencies_audit",
    # Tier 3
    "task_nightly_optimizer",
    "task_meta_optimizer",
    "task_innovation_scout",
    "task_autonomy_chaos",
    "task_drift_detection",
    "task_failure_archetype_mining",
    "task_rework_convergence_audit",
    # Tier 4
    "task_memory_consolidation",
    "task_prompt_variants_rebalance",
    "task_benchmarks_run",
    # Tier 5
    "task_cost_report_generation",
    "task_agent_performance_report",
    "task_coverage_report",
    # Tier 6
    "task_regulatory_dz_poll",
    "task_browser_contract_verify",
    # Tier 7
    "task_backup_database",
]
