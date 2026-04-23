"""Upgrade 29 - Quorum Judge : 3 instances de Judge, vote majoritaire.

Chaque instance applique le meme bareme mais avec des seuils legerement
decales (severe / standard / lenient) pour capturer le desaccord. Si les
3 verdicts divergent, la decision est marquee `disagreement=true` et le
verdict final est le SOFT_FAIL le plus conservatif.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast
from uuid import UUID

import asyncpg

from app.orchestration.tri_brain import CriticIssue, JudgeDecision

_Verdict = Literal["approve", "refine", "reject"]


_JUDGE_PROFILES: dict[str, dict[str, int]] = {
    "severe":   {"max_critical": 0, "max_major": 1},
    "standard": {"max_critical": 0, "max_major": 3},
    "lenient":  {"max_critical": 1, "max_major": 5},
}


def _judge_with_profile(issues: list[CriticIssue], profile: str) -> JudgeDecision:
    cfg = _JUDGE_PROFILES[profile]
    critical = sum(1 for i in issues if i.severity == "critical")
    major = sum(1 for i in issues if i.severity == "major")
    minor = sum(1 for i in issues if i.severity == "minor")

    verdict: _Verdict
    if critical > cfg["max_critical"]:
        verdict = "reject"
        rationale = f"{profile}: critical={critical} > {cfg['max_critical']}"
    elif major > cfg["max_major"]:
        verdict = "refine"
        rationale = f"{profile}: major={major} > {cfg['max_major']}"
    else:
        verdict = "approve"
        rationale = f"{profile}: sous seuils"
    return JudgeDecision(
        verdict=cast(_Verdict, verdict), critical_count=critical, major_count=major,
        minor_count=minor, rationale=rationale,
    )


@dataclass
class QuorumResult:
    verdicts: list[JudgeDecision]
    final_verdict: str
    has_disagreement: bool
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_verdict": self.final_verdict,
            "has_disagreement": self.has_disagreement,
            "rationale": self.rationale,
            "verdicts": [
                {"verdict": v.verdict, "critical": v.critical_count,
                 "major": v.major_count, "minor": v.minor_count,
                 "rationale": v.rationale}
                for v in self.verdicts
            ],
        }


def decide(issues: list[CriticIssue]) -> QuorumResult:
    """3 juges independants -> vote majoritaire. Desaccord => SOFT_FAIL."""
    verdicts = [
        _judge_with_profile(issues, "severe"),
        _judge_with_profile(issues, "standard"),
        _judge_with_profile(issues, "lenient"),
    ]
    vote_counts = {"approve": 0, "refine": 0, "reject": 0}
    for v in verdicts:
        vote_counts[v.verdict] += 1
    # Majorite absolue (>= 2/3)
    final = max(vote_counts, key=lambda k: vote_counts[k])
    disagreement = vote_counts[final] < 3
    if disagreement and final == "approve":
        # conservatisme : si pas unanime sur approve, on degrade vers refine
        final = "refine"
    rationale = (f"Votes : severe={verdicts[0].verdict} "
                 f"standard={verdicts[1].verdict} lenient={verdicts[2].verdict}. "
                 f"Majorite={final}, desaccord={disagreement}.")
    return QuorumResult(
        verdicts=verdicts, final_verdict=final,
        has_disagreement=disagreement, rationale=rationale,
    )


async def log_decision(
    pool: asyncpg.Pool, task_id: str, result: QuorumResult,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO quorum_decisions
              (task_id, judge_1_verdict, judge_2_verdict, judge_3_verdict,
               final_verdict, has_disagreement, rationale)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            UUID(task_id),
            result.verdicts[0].verdict, result.verdicts[1].verdict,
            result.verdicts[2].verdict, result.final_verdict,
            result.has_disagreement, result.rationale,
        )
