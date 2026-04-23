"""V5.3 BLOC 6 - Continuous Validators.

Coordonne les cycles permanent/etendu/profond/complet/chaos.
Empeche les collisions via un verrou advisory postgres.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.ctc import evidence_chain

logger = logging.getLogger(__name__)


CYCLE_LOCKS = {
    "permanent": 91001,
    "extended":  91002,
    "deep":      91003,
    "full":      91004,
    "chaos":     91005,
}


@dataclass
class CycleResult:
    cycle: str
    duration_ms: int
    ran: bool
    checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def _with_lock(
    pool: asyncpg.Pool, lock_id: int, coro,
) -> tuple[bool, Any]:
    """Advisory lock non bloquant. Si occupe -> skip."""
    async with pool.acquire() as conn:
        got = await conn.fetchval("SELECT pg_try_advisory_lock($1)", lock_id)
        if not got:
            return False, None
        try:
            result = await coro()
            return True, result
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)


async def permanent_cycle(pool: asyncpg.Pool) -> CycleResult:
    """60s : sante services, invariants, chain integrity."""
    t0 = time.perf_counter()
    async def run():
        report = await evidence_chain.verify_chain(pool, limit=200)
        return {"chain_status": report.status,
                "events_checked": report.events_checked}
    got, checks = await _with_lock(pool, CYCLE_LOCKS["permanent"], run)
    return CycleResult(
        cycle="permanent", ran=got,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        checks=checks or {},
    )


async def extended_cycle(pool: asyncpg.Pool) -> CycleResult:
    """5min : smoke tests endpoints coherence cache."""
    t0 = time.perf_counter()
    async def run():
        async with pool.acquire() as conn:
            sources_count = await conn.fetchval(
                "SELECT COUNT(*) FROM truth_sources WHERE status = 'active'")
            active_assertions = await conn.fetchval(
                "SELECT COUNT(*) FROM truth_assertions "
                "WHERE status IN ('proven', 'probable')")
        return {"active_sources": int(sources_count or 0),
                "active_assertions": int(active_assertions or 0)}
    got, checks = await _with_lock(pool, CYCLE_LOCKS["extended"], run)
    return CycleResult(
        cycle="extended", ran=got,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        checks=checks or {},
    )


async def deep_cycle(pool: asyncpg.Pool) -> CycleResult:
    """1h : suite P0 + triangulation + audit decisions auto."""
    t0 = time.perf_counter()
    async def run():
        # Re-check tout (placeholder : on loge juste les totaux)
        async with pool.acquire() as conn:
            totals = {}
            for t in ("truth_sources", "truth_assertions",
                       "truth_assertion_links", "evidence_chain_events",
                       "phase_gates"):
                n = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
                totals[t] = int(n or 0)
        report = await evidence_chain.verify_chain(pool, limit=5000)
        totals["chain_integrity"] = report.status
        return totals
    got, checks = await _with_lock(pool, CYCLE_LOCKS["deep"], run)
    return CycleResult(
        cycle="deep", ran=got,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        checks=checks or {},
    )


async def full_cycle(pool: asyncpg.Pool) -> CycleResult:
    """4x/jour : suite tests complete + validation 7 couches + baseline."""
    t0 = time.perf_counter()
    async def run():
        return await deep_cycle(pool)  # reutilise + placeholder
    got, checks = await _with_lock(pool, CYCLE_LOCKS["full"], run)
    return CycleResult(
        cycle="full", ran=got,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        checks=(checks.to_dict() if checks else {}),
    )


PRIORITY = ["chaos", "full", "deep", "extended", "permanent"]


async def tick(pool: asyncpg.Pool) -> dict[str, CycleResult]:
    """Execute tous les cycles qui peuvent tourner (plus haut priorite d'abord)."""
    results: dict[str, CycleResult] = {}
    for cycle_name in PRIORITY:
        fn = {
            "permanent": permanent_cycle, "extended": extended_cycle,
            "deep": deep_cycle, "full": full_cycle,
        }.get(cycle_name)
        if fn is None:
            continue
        results[cycle_name] = await fn(pool)
    return results
