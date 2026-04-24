"""V5.4 - Constitutional AI (Anthropic 2022).

7 principes P1..P7. Si violation -> regen avec contraintes renforcees.
"""
from __future__ import annotations

import re

from app.cognition.reasoning_trace_models import ConstitutionalReport

PRINCIPLES: dict[str, str] = {
    "P1": ("SECURITE : ne jamais compromettre utilisateurs/donnees sensibles. "
           "Respecter RGPD/CNIL/loi DZ 18-07."),
    "P2": ("CONFORMITE : respecter legislation DZ. Moteur fiscal deterministe "
           "NON OVERRIDE. Pas de creation auto d'obligations legales."),
    "P3": ("HONNETETE : jamais affirmer sans verifier. Declarer explicitement "
           "incertitudes. Zero hallucination."),
    "P4": ("SERVICE AHMED : minimiser interventions humaines. Maximiser valeur. "
           "Contrat A/B/C strict."),
    "P5": ("QUALITE : jamais livrer sans validation. Evidence-based completion. "
           "Continuous improvement."),
    "P6": ("REVERSIBILITE : toujours permettre rollback. Preserver historique. "
           "Actions reversibles preferees."),
    "P7": ("TRANSPARENCE : toujours tracer decisions. Explicabilite choix. "
           "Audit trail complet."),
}


# Patterns de detection violations (heuristiques text-based)
VIOLATION_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "P1": [
        re.compile(r"\b(leak|bypass auth|expose secret|raw password)\b", re.I),
        re.compile(r"\bsend(ing)? (pii|personal data) (to|via) (unknown|http://)\b", re.I),
    ],
    "P2": [
        re.compile(r"\b(override|bypass).+(fiscal|compliance|cnas|irg|tva)\b", re.I),
        re.compile(r"\bcontourner\b.+(loi|regle|compliance)", re.I),
    ],
    "P3": [
        re.compile(r"\bi am 100\s?% sure\b", re.I),
        re.compile(r"\bdefinitely will work\b", re.I),
        re.compile(r"\bcertitude absolue\b", re.I),
    ],
    "P4": [
        re.compile(r"\bask (ahmed|human|user)\b.+(everything|chaque)", re.I),
        re.compile(r"\bescalate without trying\b", re.I),
    ],
    "P5": [
        re.compile(r"\bship (without|sans) (test|validation)\b", re.I),
        re.compile(r"\bdeploy quick and dirty\b", re.I),
    ],
    "P6": [
        re.compile(r"\b(irreversible|no rollback)\b", re.I),
        re.compile(r"\bdrop (table|database)\b", re.I),
    ],
    "P7": [
        re.compile(r"\bhide (from|this) (log|audit|trace)\b", re.I),
        re.compile(r"\bskip audit\b", re.I),
    ],
}


def check_principle(text: str, principle: str) -> tuple[bool, str | None]:
    """Retourne (passed, violation_reason)."""
    if principle not in PRINCIPLES:
        raise KeyError(f"unknown principle {principle}")
    patterns = VIOLATION_PATTERNS.get(principle, [])
    for p in patterns:
        m = p.search(text or "")
        if m:
            return False, f"{principle}: pattern matched '{m.group(0)[:80]}'"
    return True, None


def check_all(text: str) -> ConstitutionalReport:
    results: dict[str, bool] = {}
    violations: list[dict[str, str]] = []
    for p in PRINCIPLES:
        ok, reason = check_principle(text, p)
        results[p] = ok
        if not ok and reason:
            violations.append({"principle": p, "reason": reason})
    final_pass = all(results.values())
    constraints: list[str] = []
    if not final_pass:
        for v in violations:
            constraints.append(
                f"Regen: respecter {v['principle']} ({PRINCIPLES[v['principle']][:60]})")
    return ConstitutionalReport(
        principle_results=results,
        violations=violations,
        regeneration_constraints=constraints,
        final_pass=final_pass,
    )


def build_regen_prompt(
    original_prompt: str, violations: list[dict[str, str]],
) -> str:
    """Prompt regeneration avec contraintes renforcees explicites."""
    constraint_text = "\n".join(
        f"- {v['principle']}: {PRINCIPLES[v['principle']]}"
        for v in violations
    )
    return (f"{original_prompt}\n\n"
            f"CONTRAINTES RENFORCEES (principes constitutionnels violes) :\n"
            f"{constraint_text}\n"
            f"Reformule ta reponse en respectant STRICTEMENT ces principes.")
