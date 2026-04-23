"""Upgrade 27 - EdgeHunter : analyse code + spec pour suggerer des cas limites
non couverts (timezone, overflow, race condition, nullable, currency rounding).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PATTERNS: list[tuple[str, str, str]] = [
    ("datetime_no_tz",
     r"datetime\.now\(\)|datetime\.utcnow\(\)",
     "Timezone-naive datetime : ajouter tzinfo explicite (UTC ou Africa/Algiers)"),
    ("int_overflow_risk",
     r"int\(.*\*.*\*.*\)|int\(.*\*\*",
     "Multiplication entiere pouvant overflow : envisager Decimal ou clamp"),
    ("float_money",
     r"(?i)(prix|montant|salaire|total).*:\s*float",
     "Montants en float : utiliser Decimal pour eviter les erreurs d'arrondi"),
    ("race_async_write",
     r"async def.*:\s*\n(?:[^{]*?)(_store|_cache)\[",
     "Ecriture async sans verrou sur store partage : risque de race condition"),
    ("nullable_not_handled",
     r"\.get\([^)]+\)\s*\.[a-z]",
     "`.get(x).method()` sans check None : raise AttributeError si absent"),
    ("unbounded_input",
     r"def .+\(.*text:\s*str\b(?!.*max_length)",
     "Input texte sans max_length : risque DoS"),
    ("regex_greedy",
     r"\.\*[^?]",
     "Regex glouton (.*) : risque catastrophic backtracking"),
    ("mutable_default",
     r"def .+\(.+=\s*\[\]",
     "Default argument mutable : bug classique Python"),
    ("currency_rounding",
     r"round\([^,)]+\)",
     "round() sans specification : preferer quantize(Decimal('0.01'))"),
]


@dataclass
class EdgeCase:
    kind: str
    path: str | None
    hint: str
    evidence: str


def hunt(files: dict[str, str]) -> list[EdgeCase]:
    """Retourne la liste des cas limites plausibles detectes dans le code."""
    out: list[EdgeCase] = []
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        for kind, pat, hint in PATTERNS:
            for m in re.finditer(pat, content):
                excerpt = content[max(0, m.start()-30):m.end()+30].replace("\n", " ")
                out.append(EdgeCase(kind=kind, path=path, hint=hint,
                                     evidence=excerpt.strip()[:120]))
                if len([e for e in out if e.kind == kind]) >= 3:
                    break
    return out[:20]


def summarize(cases: list[EdgeCase]) -> dict:
    by_kind: dict[str, int] = {}
    for c in cases:
        by_kind[c.kind] = by_kind.get(c.kind, 0) + 1
    return {
        "total": len(cases),
        "by_kind": by_kind,
        "top_3": [{"kind": c.kind, "path": c.path, "hint": c.hint}
                  for c in cases[:3]],
    }
