"""Upgrade 9 - Detecteur d'ambiguites : contradictions + manques + hypotheses risquees.

Reutilise le contradiction_detector V4.1 pour les conflits logiques, et y
ajoute :
- Manques : champs essentiels absents (domaine, juridiction, stack cible, SLA)
- Hypotheses risquees : termes vagues ("idealement", "si possible", "plus tard")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.intake.requirement_extractor import ExtractedSpec
from app.orchestration.contradiction_detector import Contradiction
from app.orchestration.contradiction_detector import detect as detect_contra

VAGUE_HINTS = (
    r"\b(idealement|si possible|plus tard|a voir|tbd|to[- ]be[- ]determined)\b",
    r"\b(peut-etre|peut etre|eventuellement|probablement)\b",
    r"\b(comme d'hab|comme avant|comme discute)\b",
)

MISSING_ASPECTS = {
    "target_platform": r"\b(linux|windows|docker|kubernetes|aws|azure|gcp)\b",
    "language_stack": r"\b(python|node|typescript|java|go|rust|php)\b",
    "data_volume":    r"\b(\d+\s*(?:k|m|g)?(?:b|o)\b|ligne|record|utilisateur)",
    "sla":            r"\b(sla|uptime|p\d{2}|rto|rpo|latence)\b",
    "auth":           r"\b(auth|jwt|oauth|sso|login)\b",
}


@dataclass
class AmbiguityReport:
    contradictions: list[Contradiction] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)
    vague_statements: list[str] = field(default_factory=list)
    risky_assumptions: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return bool(self.contradictions) or len(self.missing_aspects) >= 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "blocking": self.blocking,
            "contradictions": [
                {"rule": c.rule, "a": c.side_a, "b": c.side_b}
                for c in self.contradictions
            ],
            "missing_aspects": self.missing_aspects,
            "vague_statements": self.vague_statements[:10],
            "risky_assumptions": self.risky_assumptions[:10],
        }


def detect(spec: ExtractedSpec, full_text: str) -> AmbiguityReport:
    contradictions = detect_contra(full_text)
    missing = [
        asp for asp, pat in MISSING_ASPECTS.items()
        if not re.search(pat, full_text, re.IGNORECASE)
    ]
    vague: list[str] = []
    for pat in VAGUE_HINTS:
        vague.extend(m.group(0) for m in re.finditer(pat, full_text, re.IGNORECASE))

    risky: list[str] = []
    if spec.overall_complexity == "high" and "tests" not in full_text.lower():
        risky.append("complexite elevee sans politique de tests explicite")
    if spec.domain_report.jurisdiction == "DZ" and "compliance" not in full_text.lower() \
            and "conformite" not in full_text.lower():
        risky.append("juridiction DZ sans mention explicite de conformite fiscale")
    if len(spec.requirements) == 1 and len(full_text) < 200:
        risky.append("spec monolithique - risque d'under-specification")

    return AmbiguityReport(
        contradictions=contradictions,
        missing_aspects=missing,
        vague_statements=vague,
        risky_assumptions=risky,
    )
