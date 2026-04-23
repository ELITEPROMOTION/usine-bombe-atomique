"""Upgrade 21 - Reason-Code Reprompt : interdiction de relancer le LLM
sans justification precise. Toute demande de reprompt doit fournir :

- reason_code : enum stable
- file_path   : fichier concerne (null si global)
- line        : ligne si applicable
- proof_missing : ce qui manque (tests failed, secret found, etc.)

`validate()` leve ValueError sur reprompt aveugle.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ReasonCode(str, Enum):
    CRITIC_REJECT      = "CRITIC_REJECT"
    PYTEST_FAIL        = "PYTEST_FAIL"
    RUFF_ISSUES        = "RUFF_ISSUES"
    SECURITY_FINDING   = "SECURITY_FINDING"
    LEVEL0_BROKEN      = "LEVEL0_BROKEN"
    CONTRACT_MISMATCH  = "CONTRACT_MISMATCH"
    DZ_NONCOMPLIANCE   = "DZ_NONCOMPLIANCE"
    HUMAN_OVERRIDE     = "HUMAN_OVERRIDE"


@dataclass
class RepromptRequest:
    reason_code: ReasonCode
    file_path: str | None = None
    line: int | None = None
    proof_missing: str = ""
    rationale: str = ""


def validate(req: RepromptRequest) -> None:
    """Leve ValueError si la demande est incomplete (reprompt aveugle interdit)."""
    if not isinstance(req.reason_code, ReasonCode):
        raise ValueError("reason_code manquant ou invalide")
    if not req.proof_missing and req.reason_code != ReasonCode.HUMAN_OVERRIDE:
        raise ValueError(f"proof_missing obligatoire pour {req.reason_code.value}")
    needs_location = {ReasonCode.PYTEST_FAIL, ReasonCode.RUFF_ISSUES,
                       ReasonCode.SECURITY_FINDING, ReasonCode.LEVEL0_BROKEN}
    if req.reason_code in needs_location and not req.file_path:
        raise ValueError(f"file_path obligatoire pour {req.reason_code.value}")


def ensure_non_blind(**kwargs) -> RepromptRequest:
    """Constructeur defensif : leve si les arguments ne valident pas."""
    req = RepromptRequest(**kwargs)
    validate(req)
    return req
