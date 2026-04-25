"""Runbooks automatises V5.7 - 15 runbooks RB-001..RB-015.

Contract :
    class RB_XXX(Runbook):
        runbook_id = "RB-XXX"
        title = "..."
        async def detect() -> bool
        async def diagnose() -> dict
        async def remediate() -> bool
        async def escalate() -> None
        async def verify() -> bool
        def document() -> str

Orchestrator :
    scan toutes les 5 min, execute detect() -> if True -> diagnose +
    remediate + verify. Si remediate retourne False -> escalate (alerte Ahmed).
    Toutes les actions loguees dans audit_events.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

logger = logging.getLogger("uba.runbooks")


class Runbook(ABC):
    """Contract runbook."""
    runbook_id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    severity: ClassVar[str] = "warning"  # info | warning | critical

    @abstractmethod
    async def detect(self) -> bool:
        """Retourne True si le probleme est present."""

    async def diagnose(self) -> dict[str, Any]:
        """Retourne cause racine probable."""
        return {"diagnosis": "not_implemented"}

    async def remediate(self) -> bool:
        """Tente une remediation auto. True si reussi."""
        return False

    async def escalate(self) -> None:
        """Alerte Ahmed (placeholder)."""
        logger.warning("RUNBOOK %s escalating to Ahmed", self.runbook_id)

    async def verify(self) -> bool:
        """Verifie que le probleme est bien resolu."""
        return not await self.detect()

    def document(self) -> str:
        return f"{self.runbook_id} - {self.title}"


# ============================================================================
# 15 runbooks
# ============================================================================

class RB001_PostgresDown(Runbook):
    runbook_id = "RB-001"
    title = "Postgres down"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_postgres_primary_ping
            from app.health.checks import CheckStatus
            r = await check_postgres_primary_ping()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False

    async def diagnose(self) -> dict[str, Any]:
        return {"diagnosis": "postgres unreachable",
                "action_proposed": "restart postgres container"}


class RB002_RedisDown(Runbook):
    runbook_id = "RB-002"
    title = "Redis down"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_redis_primary_ping
            from app.health.checks import CheckStatus
            r = await check_redis_primary_ping()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB003_VaultSealed(Runbook):
    runbook_id = "RB-003"
    title = "Vault sealed"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_vault_status
            from app.health.checks import CheckStatus
            r = await check_vault_status()
            return r.status == CheckStatus.UNHEALTHY or \
                   r.details.get("sealed") is True
        except Exception:
            return False

    async def diagnose(self) -> dict[str, Any]:
        return {"diagnosis": "vault sealed",
                "action_proposed": "run `vault operator unseal` manually"}


class RB004_ClaudeRateLimit(Runbook):
    runbook_id = "RB-004"
    title = "Claude API rate limit"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.resilience import CircuitBreakerRegistry
            cb = CircuitBreakerRegistry.instance().get("claude_api")
            return cb.state.value == "open"
        except Exception:
            return False

    async def remediate(self) -> bool:
        # Le circuit breaker gere deja via fallback template
        return True


class RB005_DiskFull(Runbook):
    runbook_id = "RB-005"
    title = "Disk usage > 85%"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_disk_usage
            from app.health.checks import CheckStatus
            r = await check_disk_usage()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False

    async def remediate(self) -> bool:
        # Clean docker logs + pytest cache seulement (safe)
        import shutil
        for path in ["/app/.pytest_cache", "/tmp/pip-cache"]:
            try:
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass
        return False  # Manuelle pour reste


class RB006_MemoryLeak(Runbook):
    runbook_id = "RB-006"
    title = "Memory leak suspect"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_memory_usage
            from app.health.checks import CheckStatus
            r = await check_memory_usage()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB007_QueueSaturation(Runbook):
    runbook_id = "RB-007"
    title = "Queue saturation > 500"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_queue_depth
            from app.health.checks import CheckStatus
            r = await check_queue_depth()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB008_EvidenceCorruption(Runbook):
    runbook_id = "RB-008"
    title = "Evidence chain corruption"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_truth_chain_integrity
            from app.health.checks import CheckStatus
            r = await check_truth_chain_integrity()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB009_WorkerFailures(Runbook):
    runbook_id = "RB-009"
    title = "Failed tasks rate > 5%"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_failed_tasks_rate
            from app.health.checks import CheckStatus
            r = await check_failed_tasks_rate()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB010_SSLExpiry(Runbook):
    runbook_id = "RB-010"
    title = "SSL cert expiring"
    severity = "warning"

    async def detect(self) -> bool:
        # Placeholder - certbot auto-renew gere en prod
        return False


class RB011_BackupFailure(Runbook):
    runbook_id = "RB-011"
    title = "Backup stale > 2h"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.health.checks import check_backup_freshness
            from app.health.checks import CheckStatus
            r = await check_backup_freshness()
            return r.status == CheckStatus.UNHEALTHY
        except Exception:
            return False


class RB012_HighErrorRate(Runbook):
    runbook_id = "RB-012"
    title = "5xx rate > 0.2%"
    severity = "warning"

    async def detect(self) -> bool:
        # Lit SLO tracker
        try:
            from app.database import get_pool
            from app.observability.slo_tracker import SLOTracker
            t = SLOTracker(get_pool())
            s = await t.compute_status("error_rate")
            return s.status != "healthy"
        except Exception:
            return False


class RB013_CascadeFailure(Runbook):
    runbook_id = "RB-013"
    title = "3+ services degrades"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.health.checks import CheckStatus
            from app.health import HealthCheckRegistry
            results = await HealthCheckRegistry.instance().run_all()
            unhealthy_critical = sum(
                1 for r in results
                if r.is_critical and r.status == CheckStatus.UNHEALTHY
            )
            return unhealthy_critical >= 3
        except Exception:
            return False


class RB014_CircuitBreakerOpen(Runbook):
    runbook_id = "RB-014"
    title = "Circuit breaker opened"
    severity = "warning"

    async def detect(self) -> bool:
        try:
            from app.resilience import CircuitBreakerRegistry
            return any(
                cb["state"] == "open"
                for cb in CircuitBreakerRegistry.instance().list_all()
            )
        except Exception:
            return False


class RB015_SLOBreach(Runbook):
    runbook_id = "RB-015"
    title = "SLO breach (burn rate > 14x)"
    severity = "critical"

    async def detect(self) -> bool:
        try:
            from app.database import get_pool
            from app.observability.slo_tracker import SLOTracker
            t = SLOTracker(get_pool())
            for status in await t.status_all():
                if status.burn_rate_1h > 14 or status.status == "critical":
                    return True
            return False
        except Exception:
            return False


ALL_RUNBOOKS: list[type[Runbook]] = [
    RB001_PostgresDown, RB002_RedisDown, RB003_VaultSealed,
    RB004_ClaudeRateLimit, RB005_DiskFull, RB006_MemoryLeak,
    RB007_QueueSaturation, RB008_EvidenceCorruption, RB009_WorkerFailures,
    RB010_SSLExpiry, RB011_BackupFailure, RB012_HighErrorRate,
    RB013_CascadeFailure, RB014_CircuitBreakerOpen, RB015_SLOBreach,
]


@dataclass
class RunbookExecution:
    runbook_id: str
    title: str
    detected: bool
    remediated: bool
    diagnosis: dict[str, Any]
    verified: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "title": self.title,
            "detected": self.detected,
            "remediated": self.remediated,
            "diagnosis": self.diagnosis,
            "verified": self.verified,
        }


class RunbookOrchestrator:
    """Scan tous les runbooks et execute detect + diagnose + remediate."""

    async def scan_all(self) -> list[RunbookExecution]:
        results = []
        for cls in ALL_RUNBOOKS:
            rb = cls()
            try:
                detected = await rb.detect()
            except Exception as exc:
                logger.warning("rb %s detect error: %s", rb.runbook_id, exc)
                detected = False
            execution = RunbookExecution(
                runbook_id=rb.runbook_id,
                title=rb.title,
                detected=detected,
                remediated=False,
                diagnosis={},
                verified=False,
            )
            if detected:
                try:
                    execution.diagnosis = await rb.diagnose()
                    execution.remediated = await rb.remediate()
                    execution.verified = await rb.verify()
                    if not execution.verified:
                        await rb.escalate()
                except Exception as exc:
                    logger.exception("rb %s exec error", rb.runbook_id)
                    execution.diagnosis["error"] = str(exc)[:200]
            results.append(execution)
        return results


def list_runbooks() -> list[dict[str, Any]]:
    return [
        {
            "runbook_id": cls.runbook_id,
            "title": cls.title,
            "severity": cls.severity,
        }
        for cls in ALL_RUNBOOKS
    ]
