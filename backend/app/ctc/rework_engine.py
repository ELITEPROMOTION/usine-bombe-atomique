"""V5.3 BLOC 8 - Rework Engine.

Taxonomie : MINOR / MAJOR / CRITICAL / CATASTROPHIC
Strategies correspondantes + detection systemique > 3 iterations.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


MINOR_PATTERNS = ("warning", "style", "unused import", "whitespace", "format")
MAJOR_PATTERNS = ("test fail", "type error", "incoherence")
CRITICAL_PATTERNS = ("invariant", "security breach", "cve critical",
                      "secret exposed", "unauthorized")
CATASTROPHIC_PATTERNS = ("corruption", "data loss", "chain break",
                          "ledger corrupted")


@dataclass
class Anomaly:
    kind: str
    text: str
    repeat_count: int = 1
    source: str = "unknown"


@dataclass
class ReworkPlan:
    severity: str            # minor|major|critical|catastrophic
    action: str              # auto_fix|llm_rca|arret_rollback|kill_switch
    auto_apply: bool
    escalate: bool
    systemic: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__


def classify(a: Anomaly) -> str:
    t = (a.text or "").lower()
    if any(p in t for p in CATASTROPHIC_PATTERNS):
        return "catastrophic"
    if any(p in t for p in CRITICAL_PATTERNS):
        return "critical"
    if any(p in t for p in MAJOR_PATTERNS):
        return "major"
    if any(p in t for p in MINOR_PATTERNS):
        return "minor"
    return "major"  # defaut prudent


def plan(a: Anomaly) -> ReworkPlan:
    sev = classify(a)
    systemic = a.repeat_count >= 3
    if sev == "catastrophic":
        return ReworkPlan(
            severity=sev, action="kill_switch",
            auto_apply=False, escalate=True, systemic=systemic,
            details={"alert": "E4_CATASTROPHIC",
                     "next_step": "restore_from_snapshot + audit"})
    if sev == "critical":
        return ReworkPlan(
            severity=sev, action="arret_rollback",
            auto_apply=True, escalate=True, systemic=systemic,
            details={"alert": "E3_CRITICAL", "rollback": True})
    if sev == "major":
        return ReworkPlan(
            severity=sev, action="llm_rca",
            auto_apply=not systemic, escalate=systemic, systemic=systemic,
            details={"model": "sonnet", "expected_attempts": 3})
    # minor
    return ReworkPlan(
        severity=sev, action="auto_fix",
        auto_apply=True, escalate=False, systemic=systemic,
        details={"tools": ["ruff --fix", "black"]})


def should_escalate_systemic(repeat_count: int, threshold: int = 3) -> bool:
    return repeat_count >= threshold
