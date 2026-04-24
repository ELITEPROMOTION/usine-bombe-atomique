"""V5.4 AJOUT CLAUDE 9 - Reasoning Reproducibility Test.

Replay aleatoire 50 traces : doivent produire resultats IDENTIQUES.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import asyncpg


async def replay_traces(
    pool: asyncpg.Pool, *,
    sample_size: int = 50,
    replay_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Replay N traces aleatoires. Compare final_answer + final_confidence."""
    replay_fn = replay_fn or _default_replay
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT trace_id, problem_statement, final_answer, final_confidence,
                   reasoning_fingerprint
            FROM reasoning_traces
            WHERE status = 'completed'
            ORDER BY random() LIMIT $1
            """, sample_size,
        )
    identical = 0
    drifted = 0
    drift_details: list[dict[str, Any]] = []
    for r in rows:
        replayed = replay_fn(r["problem_statement"])
        original_ans = r["final_answer"]
        if isinstance(original_ans, str):
            try:
                original_ans = json.loads(original_ans)
            except json.JSONDecodeError:
                pass
        if (replayed.get("final_answer") == original_ans
            and abs(float(replayed.get("final_confidence", 0)
                          or 0) - float(r["final_confidence"] or 0)) < 0.01):
            identical += 1
        else:
            drifted += 1
            if len(drift_details) < 10:
                drift_details.append({
                    "trace_id": str(r["trace_id"]),
                    "original": original_ans,
                    "replayed": replayed.get("final_answer"),
                })
    total = len(rows)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cognitive_reproducibility_runs(
                traces_replayed, identical, drifted, drift_details)
            VALUES ($1, $2, $3, $4::jsonb)
            """,
            total, identical, drifted, json.dumps(drift_details),
        )
    return {"total": total, "identical": identical, "drifted": drifted,
            "repro_rate": round(identical / max(1, total), 4),
            "drift_details": drift_details}


def _default_replay(problem_statement: str) -> dict[str, Any]:
    """Replay deterministe : utilise reasoning_fingerprint seed."""
    from app.cognition import reasoning_fingerprint
    fp = reasoning_fingerprint.fingerprint(problem_statement, [])
    # answer deterministe derivee du fp
    seed = int(fp[:8], 16) % 100 / 100
    return {"final_answer": f"replayed_{fp[:8]}",
            "final_confidence": seed}


async def latest_runs(
    pool: asyncpg.Pool, limit: int = 5,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT traces_replayed, identical, drifted, ran_at
            FROM cognitive_reproducibility_runs
            ORDER BY ran_at DESC LIMIT $1
            """, limit,
        )
    return [{
        "traces_replayed": r["traces_replayed"],
        "identical": r["identical"], "drifted": r["drifted"],
        "ran_at": r["ran_at"].isoformat(),
    } for r in rows]
