"""SLO/SLI tracker V5.7 - fiabilite 99.8% mesurable.

Formulaire error budget :
    budget = (1 - target) * window
    Pour 99.8% sur 30j : 0.002 * 43200 min = 86.4 min autorisees

Burn rate :
    fast (1h window) : 14.4x = budget / 14.4h consommation continue
    slow (6h window) : 6x   = budget / 6j consommation continue
    Alerte si burn > seuil.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger("uba.slo")


@dataclass
class SLODefinition:
    slo_name: str
    description: str
    target_percent: float
    window_days: int
    sli_type: str


@dataclass
class SLOStatus:
    slo_name: str
    target_percent: float
    current_sli: float
    error_budget_minutes: float
    error_budget_remaining_minutes: float
    burn_rate_1h: float  # x = consumption rate vs allocation
    burn_rate_6h: float
    status: str  # healthy | warn | critical
    incident_active: bool


class SLOTracker:
    """Calcule + persiste les SLI, detecte breaches, alerte Ahmed."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def list_definitions(self) -> list[SLODefinition]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT slo_name, description, target_percent,
                       window_days, sli_type
                FROM slo_definitions
                ORDER BY slo_name
                """,
            )
        return [
            SLODefinition(
                slo_name=r["slo_name"],
                description=r["description"],
                target_percent=float(r["target_percent"]),
                window_days=int(r["window_days"]),
                sli_type=r["sli_type"],
            )
            for r in rows
        ]

    async def record(
        self, slo_name: str, good: int, bad: int,
        sli_value: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO slo_measurements
                    (slo_name, good_count, bad_count, sli_value, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                slo_name, good, bad, sli_value,
                __import__("json").dumps(metadata or {}),
            )

    async def compute_status(self, slo_name: str) -> SLOStatus:
        defs = {d.slo_name: d for d in await self.list_definitions()}
        if slo_name not in defs:
            raise KeyError(f"Unknown SLO: {slo_name}")
        d = defs[slo_name]
        window_min = d.window_days * 24 * 60
        budget_min = (1 - d.target_percent / 100) * window_min

        async with self.pool.acquire() as conn:
            # SLI sur window complete
            row_window = await conn.fetchrow(
                """
                SELECT
                    COALESCE(SUM(good_count), 0) AS good,
                    COALESCE(SUM(bad_count), 0) AS bad
                FROM slo_measurements
                WHERE slo_name = $1
                  AND measured_at > NOW() - ($2 || ' days')::interval
                """, slo_name, str(d.window_days),
            )
            total = int(row_window["good"]) + int(row_window["bad"])
            sli = (int(row_window["good"]) / total * 100) if total else 100.0
            bad_window = int(row_window["bad"])

            # SLI sur 1h + 6h (burn rate)
            row_1h = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(bad_count), 0) AS bad,
                       COALESCE(SUM(good_count), 0) AS good
                FROM slo_measurements
                WHERE slo_name = $1
                  AND measured_at > NOW() - INTERVAL '1 hour'
                """, slo_name,
            )
            row_6h = await conn.fetchrow(
                """
                SELECT COALESCE(SUM(bad_count), 0) AS bad,
                       COALESCE(SUM(good_count), 0) AS good
                FROM slo_measurements
                WHERE slo_name = $1
                  AND measured_at > NOW() - INTERVAL '6 hours'
                """, slo_name,
            )

        def burn(bad: int, good: int, minutes: int) -> float:
            """Burn rate : taux de consommation / taux alloue."""
            total_m = bad + good
            if total_m == 0 or budget_min == 0:
                return 0.0
            bad_rate = bad / total_m
            allowed_rate = budget_min / window_min
            return bad_rate / allowed_rate if allowed_rate > 0 else 0.0

        br1 = burn(int(row_1h["bad"]), int(row_1h["good"]), 60)
        br6 = burn(int(row_6h["bad"]), int(row_6h["good"]), 360)

        # Error budget utilise = bad_window / total allocation
        budget_remaining = max(0, budget_min - bad_window)

        status = "healthy"
        if sli < d.target_percent:
            status = "critical" if br1 > 14 else "warn"
        elif br1 > 14 or br6 > 6:
            status = "warn"

        incident_active = False
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM slo_incidents
                WHERE slo_name = $1 AND ended_at IS NULL
                LIMIT 1
                """, slo_name,
            )
            incident_active = row is not None

        return SLOStatus(
            slo_name=slo_name,
            target_percent=d.target_percent,
            current_sli=round(sli, 3),
            error_budget_minutes=round(budget_min, 1),
            error_budget_remaining_minutes=round(budget_remaining, 1),
            burn_rate_1h=round(br1, 2),
            burn_rate_6h=round(br6, 2),
            status=status,
            incident_active=incident_active,
        )

    async def status_all(self) -> list[SLOStatus]:
        out = []
        for d in await self.list_definitions():
            try:
                out.append(await self.compute_status(d.slo_name))
            except Exception as exc:
                logger.warning("slo compute %s failed: %s", d.slo_name, exc)
        return out

    async def open_incident(
        self, slo_name: str, severity: str, burn_rate: float, reason: str,
    ) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO slo_incidents(slo_name, severity, burn_rate, reason)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """, slo_name, severity, burn_rate, reason,
            )
        return int(row["id"])

    async def close_incident(
        self, incident_id: int, resolution: str, resolved_auto: bool,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE slo_incidents
                SET ended_at = NOW(), resolution = $2, resolved_auto = $3
                WHERE id = $1
                """, incident_id, resolution, resolved_auto,
            )

    async def incidents(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, slo_name, started_at, ended_at, severity,
                       burn_rate, reason, resolved_auto, resolution
                FROM slo_incidents
                ORDER BY started_at DESC
                LIMIT $1
                """, limit,
            )
        return [
            {
                "id": int(r["id"]),
                "slo_name": r["slo_name"],
                "started_at": r["started_at"].isoformat(),
                "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None,
                "severity": r["severity"],
                "burn_rate": float(r["burn_rate"]) if r["burn_rate"] else None,
                "reason": r["reason"],
                "resolved_auto": bool(r["resolved_auto"]),
                "resolution": r["resolution"],
            } for r in rows
        ]
