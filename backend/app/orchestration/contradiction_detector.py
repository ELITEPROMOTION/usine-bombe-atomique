"""Contradiction Detector V4.1 - detection de contradictions logiques.

Scanne une specification pour trouver des couples mutuellement exclusifs :
- "pas de base de donnees" + "postgres/mysql/redis"
- "read-only" + "POST/PUT/DELETE"
- "aucun test" + "tests pytest requis"
- TVA 19% + TVA != 19%
- "offline only" + "API REST publique"

Une contradiction detectee declenche une escalade niveau E3
(escalator.py) avec statut `waiting_input` au lieu d'halluciner.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Contradiction:
    rule: str
    side_a: str
    side_b: str
    excerpt_a: str
    excerpt_b: str


# (pattern_a, pattern_b) : si les deux matchent, c'est une contradiction
CONTRADICTION_RULES: list[tuple[str, re.Pattern[str], re.Pattern[str]]] = [
    ("no_db_vs_db",
     re.compile(r"(?i)\b(aucun[e]? (?:base|bdd)|pas de base|no database)\b"),
     re.compile(r"(?i)\b(postgres|mysql|mariadb|mongodb|sqlite|redis)\b")),
    ("read_only_vs_writes",
     re.compile(r"(?i)\b(read[- ]only|lecture seule|immutab)\b"),
     re.compile(r"(?i)\b(POST|PUT|DELETE|PATCH)\b")),
    ("no_tests_vs_tests",
     re.compile(r"(?i)\b(aucun test|no tests?|sans tests?)\b"),
     re.compile(r"(?i)\b(pytest|unittest|tests? pytest|couverture)\b")),
    ("tva_conflict",
     re.compile(r"(?i)TVA\s*(?:a\s*)?19\s*%"),
     re.compile(r"(?i)TVA\s*(?:a\s*)?(?:17|18|20|21)\s*%")),
    ("offline_vs_public_api",
     re.compile(r"(?i)\b(offline only|hors ligne seulement|no network)\b"),
     re.compile(r"(?i)\b(API (?:REST|publique)|endpoint HTTP|webhook)\b")),
    ("stateless_vs_session",
     re.compile(r"(?i)\bstateless\b"),
     re.compile(r"(?i)\b(session (?:utilisateur|serveur)|cookie de session)\b")),
    ("no_deps_vs_fastapi",
     re.compile(r"(?i)\b(zero dependances?|aucune dependance)\b"),
     re.compile(r"(?i)\b(fastapi|django|flask|sqlalchemy|pydantic)\b")),
]


def _excerpt(text: str, match: re.Match[str], radius: int = 40) -> str:
    start = max(0, match.start() - radius)
    end = min(len(text), match.end() + radius)
    return text[start:end].replace("\n", " ").strip()


def detect(spec: str) -> list[Contradiction]:
    """Renvoie la liste des contradictions detectees dans la spec."""
    text = spec or ""
    out: list[Contradiction] = []
    for rule, pat_a, pat_b in CONTRADICTION_RULES:
        m_a = pat_a.search(text)
        m_b = pat_b.search(text)
        if m_a and m_b:
            out.append(Contradiction(
                rule=rule,
                side_a=m_a.group(0),
                side_b=m_b.group(0),
                excerpt_a=_excerpt(text, m_a),
                excerpt_b=_excerpt(text, m_b),
            ))
    return out


def format_question(contradictions: list[Contradiction]) -> str:
    """Formule UNE question d'escalade (E3) pour resoudre les contradictions."""
    if not contradictions:
        return ""
    first = contradictions[0]
    return (
        f"Contradiction detectee dans la specification : '{first.side_a}' s'oppose "
        f"a '{first.side_b}'. Contextes :\n"
        f"  A : ...{first.excerpt_a}...\n"
        f"  B : ...{first.excerpt_b}...\n"
        "Quelle est l'intention correcte ?"
    )
