"""V9HealthCheck : etat de sante des composants V9.

Returns un dict serialisable pour /health endpoint :
{
  "status": "pass" | "warn" | "fail",
  "checks": {
    "vault": {...},
    "platform_config": {...},
    "live_modes": {...},
    "evidence_chain": {...},
    "audit_triggers": {...}
  },
  "checked_at": ISO timestamp
}
"""
from __future__ import annotations

import enum
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class HealthStatus(str, enum.Enum):
    PASS = "pass"
    WARN = "warn"      # degrade mais fonctionnel
    FAIL = "fail"      # casse


@dataclass(frozen=True)
class HealthCheckResult:
    name: str
    status: HealthStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
        }


def _aggregate_status(results: list[HealthCheckResult]) -> HealthStatus:
    """Pire status parmi les checks."""
    if any(r.status is HealthStatus.FAIL for r in results):
        return HealthStatus.FAIL
    if any(r.status is HealthStatus.WARN for r in results):
        return HealthStatus.WARN
    return HealthStatus.PASS


class V9HealthCheck:
    """Health checks cross-V9. A appeler depuis /health/v9 endpoint."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def run_all(self) -> dict[str, Any]:
        results: list[HealthCheckResult] = [
            await self.check_platform_config(),
            await self.check_evidence_chain(),
            self.check_live_modes(),
            self.check_jwt_mode(),
        ]
        overall = _aggregate_status(results)
        return {
            "status": overall.value,
            "checks": {r.name: r.to_dict() for r in results},
            "checked_at": datetime.now(UTC).isoformat(),
        }

    async def check_platform_config(self) -> HealthCheckResult:
        """V9B platform_config doit exister (singleton id=1)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT version, committed_at FROM platform_config WHERE id = 1",
            )
        if row is None:
            return HealthCheckResult(
                name="platform_config",
                status=HealthStatus.FAIL,
                message="platform_config absent — Phase 9B non commitee",
            )
        return HealthCheckResult(
            name="platform_config",
            status=HealthStatus.PASS,
            message="platform_config present",
            details={
                "version": row["version"],
                "committed_at": row["committed_at"].isoformat(),
            },
        )

    async def check_evidence_chain(self) -> HealthCheckResult:
        """Evidence ledger : derniere entree existe + au moins 5 maillons."""
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM evidence_ledger",
            )
            last = await conn.fetchrow(
                """
                SELECT chain_hash, actor, created_at
                  FROM evidence_ledger ORDER BY id DESC LIMIT 1
                """,
            )
        if count is None or count == 0:
            return HealthCheckResult(
                name="evidence_chain",
                status=HealthStatus.FAIL,
                message="evidence_ledger vide",
            )
        if count < 5:
            return HealthCheckResult(
                name="evidence_chain",
                status=HealthStatus.WARN,
                message=f"evidence_ledger n'a que {count} maillons "
                        f"(attendu >= 5 pour V9 complete)",
                details={"count": int(count)},
            )
        return HealthCheckResult(
            name="evidence_chain",
            status=HealthStatus.PASS,
            message=f"evidence_ledger {count} maillons OK",
            details={
                "count": int(count),
                "last_actor": last["actor"] if last else None,
            },
        )

    def check_live_modes(self) -> HealthCheckResult:
        """Etat des gates live (UBA_LIVE_HOSTINGER, UBA_LIVE_STRIPE).

        En staging/dev : OFF attendu.
        En prod : peuvent etre ON, mais ne doivent JAMAIS etre commit dans
        CI. Ce check ne les juge pas — il les expose.
        """
        modes = {
            "hostinger": os.environ.get("UBA_LIVE_HOSTINGER", "0").strip() == "1",
            "stripe": os.environ.get("UBA_LIVE_STRIPE", "0").strip() == "1",
        }
        active = [k for k, v in modes.items() if v]
        if active:
            return HealthCheckResult(
                name="live_modes",
                status=HealthStatus.WARN,    # warn = "production mode active"
                message=f"live modes ON : {sorted(active)}",
                details=modes,
            )
        return HealthCheckResult(
            name="live_modes",
            status=HealthStatus.PASS,
            message="tous les live modes OFF (mode safe)",
            details=modes,
        )

    def check_jwt_mode(self) -> HealthCheckResult:
        """JWT_ADMIN_SECRET configure ?"""
        secret = os.environ.get("JWT_ADMIN_SECRET", "").strip()
        legacy = os.environ.get("UBA_ADMIN_TOKEN", "").strip()
        if secret and len(secret) >= 32:
            return HealthCheckResult(
                name="jwt_mode",
                status=HealthStatus.PASS,
                message="JWT mode configure",
                details={
                    "jwt_enabled": True,
                    "legacy_fallback": bool(legacy),
                },
            )
        if legacy:
            return HealthCheckResult(
                name="jwt_mode",
                status=HealthStatus.WARN,
                message="legacy admin token uniquement — migrer vers JWT",
                details={"jwt_enabled": False, "legacy_fallback": True},
            )
        return HealthCheckResult(
            name="jwt_mode",
            status=HealthStatus.FAIL,
            message="aucun mode admin configure (fail-closed)",
            details={"jwt_enabled": False, "legacy_fallback": False},
        )
