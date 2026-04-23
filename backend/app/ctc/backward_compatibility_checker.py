"""V5.3 BLOC 20 - Backward Compatibility Checker.

Replay historique et compare verdicts (version_old vs version_new).
Verdict pass si regression < 1%.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import asyncpg


MAX_REGRESSION_RATE = 0.01


@dataclass
class ReplayReport:
    version_old: str
    version_new: str
    verdicts_replayed: int
    identical: int
    improved: int
    regressed: int
    regression_details: list[dict[str, Any]]
    verdict_pass: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


async def run_replay(
    pool: asyncpg.Pool, *,
    version_old: str, version_new: str,
    old_fn: Callable[[dict[str, Any]], str],
    new_fn: Callable[[dict[str, Any]], str],
    sample_limit: int = 1000,
) -> ReplayReport:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT verdict, chain_hash, input_hash, output_hash
            FROM evidence_chain_events
            ORDER BY ts_us DESC LIMIT $1
            """, sample_limit,
        )
    identical = 0
    improved = 0
    regressed = 0
    reg_details: list[dict[str, Any]] = []
    RANK = {"HARD_FAIL": 0, "SOFT_FAIL": 1, "CONDITIONAL_PASS": 2,
            "PASS": 3, "GENESIS": 3}
    for r in rows:
        sample = {"verdict": r["verdict"], "input_hash": r["input_hash"]}
        old_v = old_fn(sample)
        new_v = new_fn(sample)
        if old_v == new_v:
            identical += 1
            continue
        if RANK.get(new_v, 0) > RANK.get(old_v, 0):
            improved += 1
        else:
            regressed += 1
            if len(reg_details) < 20:
                reg_details.append({
                    "chain_hash": r["chain_hash"][:16],
                    "old_verdict": old_v, "new_verdict": new_v,
                })
    total = len(rows) or 1
    regression_rate = regressed / total
    verdict_pass = regression_rate <= MAX_REGRESSION_RATE

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO truth_backward_replay(
                version_old, version_new, verdicts_replayed, identical,
                improved, regressed, regression_details, verdict_pass)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
            """,
            version_old[:40], version_new[:40], total,
            identical, improved, regressed,
            json.dumps(reg_details), verdict_pass,
        )
    return ReplayReport(
        version_old=version_old, version_new=version_new,
        verdicts_replayed=total,
        identical=identical, improved=improved, regressed=regressed,
        regression_details=reg_details, verdict_pass=verdict_pass,
    )


async def recent(
    pool: asyncpg.Pool, limit: int = 10,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT version_old, version_new, verdicts_replayed,
                   identical, improved, regressed, verdict_pass, run_at
            FROM truth_backward_replay ORDER BY run_at DESC LIMIT $1
            """, limit,
        )
    return [{**dict(r), "run_at": r["run_at"].isoformat()}
            for r in rows]
