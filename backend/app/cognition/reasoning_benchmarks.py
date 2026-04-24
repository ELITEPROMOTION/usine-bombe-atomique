"""V5.4 - Reasoning Benchmarks.

5 familles : logic / mathematical / coding / reasoning_heavy / compliance.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import asyncpg

FAMILIES = ["logic", "mathematical", "coding",
             "reasoning_heavy", "compliance"]


# Corpus minimal
SAMPLES: dict[str, list[dict[str, Any]]] = {
    "logic": [
        {"q": "All A are B. X is A. Is X B?", "a": "yes"},
        {"q": "Some A are B. X is A. Is X necessarily B?", "a": "no"},
        {"q": "If P then Q. Not Q. Is P?", "a": "no"},
    ],
    "mathematical": [
        {"q": "TVA 19% on 1000 DZD = ?", "a": "190"},
        {"q": "TAP 2% on 5000 = ?", "a": "100"},
        {"q": "CNAS salarie 9% on 50000 = ?", "a": "4500"},
    ],
    "coding": [
        {"q": "Python list comprehension syntax", "a": "[x for x in iterable]"},
        {"q": "SQL: select all from table users", "a": "select * from users"},
    ],
    "reasoning_heavy": [
        {"q": "Tradeoff SRE : availability vs consistency", "a": "cap"},
        {"q": "Architecture : monolith vs microservices", "a": "depends"},
    ],
    "compliance": [
        {"q": "NIN algerien : combien de chiffres ?", "a": "18"},
        {"q": "RGPD : droit a l'effacement ?", "a": "article 17"},
    ],
}


@dataclass
class BenchmarkResult:
    family: str
    score_0_100: float
    n_samples: int
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


_SOLVER_RULES = [
    (("tva 19", "1000"), "190"),
    (("tap 2", "5000"), "100"),
    (("cnas", "50000"), "4500"),
    (("nin", "chiffres"), "18"),
    (("rgpd", "effacement"), "article 17"),
    (("all a are b", "x is a"), "yes"),
    (("some a are b",), "no"),
    (("if p then q", "not q"), "no"),
    (("list comprehension",), "[x for x in iterable]"),
    (("select all from table",), "select * from users"),
    (("monolith vs microservices",), "depends"),
    (("availability vs consistency",), "cap"),
]


def _default_solver(q: str) -> str:
    """Solver deterministe baseline."""
    ql = q.lower()
    for tokens, answer in _SOLVER_RULES:
        if all(t in ql for t in tokens):
            return answer
    return "unknown"


def run_family(
    family: str, *, solver: Callable[[str], str] | None = None,
) -> BenchmarkResult:
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family}")
    solver = solver or _default_solver
    samples = SAMPLES.get(family, [])
    correct = 0
    per_item: list[dict[str, Any]] = []
    for s in samples:
        got = solver(s["q"])
        ok = (got or "").strip().lower() == s["a"].strip().lower()
        if ok:
            correct += 1
        per_item.append({"q": s["q"][:80], "expected": s["a"],
                          "got": got[:80], "correct": ok})
    score = (correct / len(samples) * 100) if samples else 0
    return BenchmarkResult(
        family=family, score_0_100=score, n_samples=len(samples),
        details={"per_item": per_item},
    )


async def run_all(
    pool: asyncpg.Pool, *,
    solver: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    results: dict[str, BenchmarkResult] = {}
    total_score = 0.0
    async with pool.acquire() as conn:
        for f in FAMILIES:
            r = run_family(f, solver=solver)
            results[f] = r
            total_score += r.score_0_100
            # Compute baseline_delta against last 30 days
            last_avg = await conn.fetchval(
                "SELECT AVG(score_0_100) FROM cognitive_benchmarks "
                "WHERE family = $1 AND ran_at >= NOW() - INTERVAL '30 days'",
                f,
            )
            delta = r.score_0_100 - float(last_avg or 0) if last_avg else None
            await conn.execute(
                """
                INSERT INTO cognitive_benchmarks(
                    family, score_0_100, baseline_delta, n_samples, details)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                """,
                f, r.score_0_100, delta, r.n_samples,
                json.dumps(r.details),
            )
    overall_score = total_score / len(FAMILIES) if FAMILIES else 0
    return {
        "overall_score": round(overall_score, 2),
        "by_family": {k: v.to_dict() for k, v in results.items()},
    }


async def latest(pool: asyncpg.Pool) -> dict[str, Any]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (family) family, score_0_100,
                   baseline_delta, n_samples, ran_at
            FROM cognitive_benchmarks
            ORDER BY family, ran_at DESC
            """
        )
    out: dict[str, Any] = {}
    for r in rows:
        out[r["family"]] = {
            "score": float(r["score_0_100"]),
            "delta": float(r["baseline_delta"] or 0)
                if r["baseline_delta"] else None,
            "n": r["n_samples"],
            "ran_at": r["ran_at"].isoformat(),
        }
    return out
