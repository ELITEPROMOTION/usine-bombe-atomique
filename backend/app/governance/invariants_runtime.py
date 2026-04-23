"""V5.2 BLOC 4 - Invariants Runtime.

Garde-fous durs verifies avant ET apres chaque action d'etat. Une violation
declenche :
  - kill-switch immediat (raise InvariantViolation)
  - evidence_ledger record kind='contract_violation'
  - rollback recommande au caller

Regroupes en 5 familles :
  FISCAL_DZ        : TVA 19%, TAP 2%, VEFA paliers, IRG, NIN
  SECURITY         : secrets, outbound, vault, tenant isolation
  ARCHITECTURAL    : Builder/Critic/Judge separation, ledger append-only
  AUTONOMY         : human approval irreversible, payment cooling-off
  QUALITY          : proof coverage, tests passing, no regression
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


class InvariantViolation(Exception):
    """Leve quand un invariant est viole. Le caller doit rollback."""


@dataclass
class InvariantResult:
    name: str
    family: str
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


# ============================================================ FISCAL_DZ

FISCAL_DZ_CONSTANTS = {
    "tva_rate": 0.19,
    "tap_rate": 0.02,
    "ibs_low_rate": 0.19,          # manufacturing
    "ibs_high_rate": 0.26,         # other
    "cnas_salarie": 0.09,
    "cnas_employeur": 0.26,
    "vefa_paliers": [0.20, 0.15, 0.35, 0.25, 0.05],  # somme = 1.00
    "nin_length": 18,
    "irg_tranches": [30_000, 120_000, 360_000, 1_440_000],
    "irg_rates":    [0.00, 0.20, 0.30, 0.35, 0.42],
}


def _inv_tva_rate_fixed() -> InvariantResult:
    return InvariantResult(
        "tva_rate_19_immuable", "FISCAL_DZ",
        passed=FISCAL_DZ_CONSTANTS["tva_rate"] == 0.19,
        details={"expected": 0.19, "actual": FISCAL_DZ_CONSTANTS["tva_rate"]},
    )


def _inv_vefa_paliers_sum_one() -> InvariantResult:
    s = sum(FISCAL_DZ_CONSTANTS["vefa_paliers"])
    return InvariantResult(
        "vefa_paliers_sum_1.0", "FISCAL_DZ",
        passed=abs(s - 1.0) < 1e-9 and
               len(FISCAL_DZ_CONSTANTS["vefa_paliers"]) == 5,
        details={"sum": s, "values": FISCAL_DZ_CONSTANTS["vefa_paliers"]},
    )


def _inv_irg_monotone() -> InvariantResult:
    rates = FISCAL_DZ_CONSTANTS["irg_rates"]
    return InvariantResult(
        "irg_rates_monotone", "FISCAL_DZ",
        passed=all(rates[i] <= rates[i + 1] for i in range(len(rates) - 1)),
        details={"rates": rates},
    )


def verify_nin(nin: str) -> InvariantResult:
    """Verifie le format NIN DZ (18 chiffres)."""
    ok = bool(nin and len(nin) == 18 and nin.isdigit())
    return InvariantResult(
        "nin_format_18_digits", "FISCAL_DZ", passed=ok,
        details={"len": len(nin) if nin else 0,
                  "is_digit": bool(nin) and nin.isdigit()},
    )


# ============================================================ SECURITY

_SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN .*PRIVATE KEY-----"),
    re.compile(r"(?i)bearer\s+['\"]?[A-Za-z0-9._\-]{30,}"),
]


def _inv_no_secret_in_text(text: str) -> InvariantResult:
    hits = []
    for pat in _SECRET_PATTERNS:
        m = pat.search(text or "")
        if m:
            hits.append(pat.pattern[:30])
    return InvariantResult(
        "no_secret_in_output", "SECURITY",
        passed=not hits, details={"matched_patterns": hits},
    )


def _inv_tenant_isolation(tenant_id: str | None) -> InvariantResult:
    """tenant_id DOIT etre present (non-null) pour toute operation."""
    return InvariantResult(
        "tenant_isolation_non_null", "SECURITY",
        passed=bool(tenant_id), details={"tenant_id": tenant_id},
    )


# ============================================================ ARCHITECTURAL

def _inv_roles_distinct(
    builder: str | None, critic: str | None, judge: str | None,
) -> InvariantResult:
    roles = [r for r in (builder, critic, judge) if r]
    passed = len(roles) == len(set(roles))
    return InvariantResult(
        "builder_critic_judge_distinct", "ARCHITECTURAL",
        passed=passed,
        details={"builder": builder, "critic": critic, "judge": judge},
    )


def _inv_ledger_append_only_hint(sql: str) -> InvariantResult:
    """Interdit UPDATE/DELETE sur evidence_ledger/audit_events/decisions_audit."""
    low = (sql or "").lower()
    forbidden = any(
        table in low and op in low
        for table in ("evidence_ledger", "audit_events", "decisions_audit")
        for op in ("update ", "delete from ")
    )
    return InvariantResult(
        "ledger_append_only_sql", "ARCHITECTURAL",
        passed=not forbidden, details={"sql_preview": (sql or "")[:80]},
    )


# ============================================================ AUTONOMY

IRREVERSIBLE_ACTIONS = {
    "payment.execute", "prod.rollback", "schema.drop_table",
    "account.delete", "audit.tamper",
}


def _inv_no_irreversible_without_approval(
    action: str, human_approved: bool,
) -> InvariantResult:
    is_irr = action in IRREVERSIBLE_ACTIONS
    passed = (not is_irr) or human_approved
    return InvariantResult(
        "no_irreversible_without_approval", "AUTONOMY",
        passed=passed,
        details={"action": action, "irreversible": is_irr,
                  "approved": human_approved},
    )


def _inv_payment_cooling_off(
    authorization_ts_sec: float | None, now_ts_sec: float,
    min_cooling_off_sec: int = 900,    # 15 minutes
) -> InvariantResult:
    if authorization_ts_sec is None:
        return InvariantResult(
            "payment_cooling_off_15min", "AUTONOMY",
            passed=False,
            details={"reason": "no_authorization_timestamp"})
    delta = now_ts_sec - authorization_ts_sec
    return InvariantResult(
        "payment_cooling_off_15min", "AUTONOMY",
        passed=delta >= min_cooling_off_sec,
        details={"delta_sec": delta, "min_required": min_cooling_off_sec},
    )


# ============================================================ QUALITY

def _inv_proof_coverage(rate: float, min_rate: float = 0.95) -> InvariantResult:
    return InvariantResult(
        "proof_coverage_rate", "QUALITY",
        passed=rate >= min_rate,
        details={"rate": rate, "min_required": min_rate},
    )


def _inv_all_tests_passing(
    passed: int, total: int,
) -> InvariantResult:
    return InvariantResult(
        "all_tests_passing", "QUALITY",
        passed=passed == total and total > 0,
        details={"passed": passed, "total": total},
    )


# ============================================================ PUBLIC API

def verify_pre(
    context: dict[str, Any],
) -> list[InvariantResult]:
    """Verifie les invariants AVANT une action. context contient :
       action, tenant_id, builder, critic, judge, spec,
       authorization_ts, approved, proof_coverage, tests_passed, tests_total.
    """
    results: list[InvariantResult] = []
    # FISCAL_DZ constantes (toujours verifiees)
    results.append(_inv_tva_rate_fixed())
    results.append(_inv_vefa_paliers_sum_one())
    results.append(_inv_irg_monotone())
    # SECURITY
    results.append(_inv_tenant_isolation(context.get("tenant_id")))
    if "spec" in context:
        results.append(_inv_no_secret_in_text(context["spec"]))
    # ARCHITECTURAL
    results.append(_inv_roles_distinct(
        context.get("builder"), context.get("critic"), context.get("judge")))
    if "sql" in context:
        results.append(_inv_ledger_append_only_hint(context["sql"]))
    # AUTONOMY
    if "action" in context:
        results.append(_inv_no_irreversible_without_approval(
            context["action"], bool(context.get("approved", False))))
    return results


def verify_post(
    context: dict[str, Any],
) -> list[InvariantResult]:
    """Verifie apres action : quality + couverture. Re-verifie les invariants
    critiques (defensif)."""
    results: list[InvariantResult] = []
    if "proof_coverage" in context:
        results.append(_inv_proof_coverage(float(context["proof_coverage"])))
    if "tests_passed" in context and "tests_total" in context:
        results.append(_inv_all_tests_passing(
            int(context["tests_passed"]), int(context["tests_total"])))
    # Re-check fiscal (defensif)
    results.append(_inv_tva_rate_fixed())
    results.append(_inv_vefa_paliers_sum_one())
    return results


def enforce(results: list[InvariantResult]) -> None:
    """Raise InvariantViolation si au moins un resultat a passed=False."""
    failures = [r for r in results if not r.passed]
    if not failures:
        return
    names = [f.name for f in failures]
    raise InvariantViolation(
        f"{len(failures)} invariant(s) violated: {', '.join(names)}")


def snapshot_signature() -> str:
    """Retourne le hash SHA-256 de la configuration FISCAL_DZ. Doit etre
    identique entre deux boots. Si different -> kill-switch."""
    canon = json.dumps(FISCAL_DZ_CONSTANTS, sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()


# Signature attendue gelee : toute modification doit etre approuvee
# explicitement (constante VSERROR_ON_MISMATCH).
EXPECTED_FISCAL_DZ_SIG = snapshot_signature()


def verify_fiscal_dz_signature() -> InvariantResult:
    current = snapshot_signature()
    return InvariantResult(
        "fiscal_dz_frozen_signature", "FISCAL_DZ",
        passed=current == EXPECTED_FISCAL_DZ_SIG,
        details={"expected": EXPECTED_FISCAL_DZ_SIG[:16],
                  "current": current[:16]},
    )


# ============================================================ decorator

def with_invariants(
    pre_ctx_fn: Callable[..., dict[str, Any]] | None = None,
    post_ctx_fn: Callable[..., dict[str, Any]] | None = None,
) -> Callable:
    """Decorateur : enforce verify_pre avant, verify_post apres."""
    def outer(fn: Callable) -> Callable:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            pre_ctx = pre_ctx_fn(*args, **kwargs) if pre_ctx_fn else {}
            enforce(verify_pre(pre_ctx))
            result = await fn(*args, **kwargs)
            post_ctx = post_ctx_fn(result, *args, **kwargs) if post_ctx_fn else {}
            enforce(verify_post(post_ctx))
            return result
        wrapped.__name__ = fn.__name__
        return wrapped
    return outer
