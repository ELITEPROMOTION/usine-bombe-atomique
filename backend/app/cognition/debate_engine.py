"""V5.4 - Debate Engine (Irving 2018 / Anthropic).

2 agents + Judge. Devil's advocate si convergence trop rapide.
Judge peut proposer HYBRID_SYNTHESIS.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.cognition.reasoning_trace_models import DebateRound, DebateTrace

MAX_ROUNDS = 5
EARLY_CONVERGENCE_ROUND = 2


ROLE_PAIRS = {
    "optimist_pessimist": ("Optimist", "Pessimist"),
    "innovation_stability": ("Innovation", "Stability"),
    "feature_techdebt":     ("Feature", "TechDebt"),
    "fast_robust":          ("Fast", "Robust"),
    "simple_complete":      ("Simple", "Complete"),
}


@dataclass
class DebateConfig:
    role_a: str
    role_b: str
    max_rounds: int = MAX_ROUNDS


def _default_speaker(
    role: str, round_index: int, other_prev: str | None,
) -> tuple[str, str | None]:
    """Deterministic speaker : produit un argument + (optionnel) counter."""
    arg = f"{role} argument round {round_index} based on prior: {other_prev or 'n/a'}"
    counter = None
    if other_prev:
        counter = f"{role} counter to previous"
    return arg, counter


def _early_convergence(rounds: list[DebateRound]) -> bool:
    """Si dernieres propositions sont quasi-identiques (naif : meme longueur)."""
    if len(rounds) < 2 * EARLY_CONVERGENCE_ROUND:
        return False
    last_two = rounds[-2:]
    return abs(len(last_two[0].argument) - len(last_two[1].argument)) < 10


def debate(
    question: str, *,
    cfg: DebateConfig | None = None,
    speaker_a: Callable[[int, str | None], tuple[str, str | None]] | None = None,
    speaker_b: Callable[[int, str | None], tuple[str, str | None]] | None = None,
    judge: Callable[[list[DebateRound]], tuple[str, str]] | None = None,
) -> DebateTrace:
    cfg = cfg or DebateConfig(role_a="Optimist", role_b="Pessimist")

    def _speaker_a(i: int, prev: str | None) -> tuple[str, str | None]:
        return _default_speaker(cfg.role_a, i, prev)

    def _speaker_b(i: int, prev: str | None) -> tuple[str, str | None]:
        return _default_speaker(cfg.role_b, i, prev)

    if speaker_a is None:
        speaker_a = _speaker_a
    if speaker_b is None:
        speaker_b = _speaker_b
    if judge is None:
        judge = _default_judge

    rounds: list[DebateRound] = []
    devils = False
    prev_b: str | None = None
    for i in range(cfg.max_rounds):
        arg_a, ctr_a = speaker_a(i, prev_b)
        rounds.append(DebateRound(
            round_index=i, role=cfg.role_a,
            argument=arg_a, counter=ctr_a))
        arg_b, ctr_b = speaker_b(i, arg_a)
        rounds.append(DebateRound(
            round_index=i, role=cfg.role_b,
            argument=arg_b, counter=ctr_b))
        prev_b = arg_b
        # Devil's advocate si convergence precoce
        if i == EARLY_CONVERGENCE_ROUND and _early_convergence(rounds):
            devils = True

    verdict, rationale = judge(rounds)
    return DebateTrace(
        role_a=cfg.role_a, role_b=cfg.role_b,
        rounds=rounds, devils_advocate_activated=devils,
        judge_verdict=verdict, judge_rationale=rationale,
    )


def _default_judge(rounds: list[DebateRound]) -> tuple[str, str]:
    """Juge deterministe : tranche selon longueur cumulee + qualite."""
    if not rounds:
        return "escalate", "no rounds"
    len_a = sum(len(r.argument) for r in rounds if r.role.endswith("A") or "timist" in r.role or "novation" in r.role or "Fast" in r.role or "Simple" in r.role or "eature" in r.role)
    len_b = sum(len(r.argument) for r in rounds) - len_a
    if abs(len_a - len_b) < 50:
        return "hybrid_synthesis", (
            f"Scores proches (A={len_a}, B={len_b}) -> synthese hybride proposee")
    if len_a > len_b:
        return "A_wins", f"A plus developpe ({len_a} > {len_b})"
    return "B_wins", f"B plus developpe ({len_b} > {len_a})"
