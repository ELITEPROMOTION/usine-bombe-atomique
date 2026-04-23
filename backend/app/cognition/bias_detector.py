"""V5.4 - Bias Detector (8 biais + mitigation active).

Detecte + applique mitigation (pas juste liste).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.cognition.reasoning_trace_models import BiasReport


BIAS_NAMES = [
    "confirmation", "anchoring", "availability",
    "sunk_cost", "overconfidence", "groupthink",
    "recency", "halo",
]


# Heuristiques texte pour detection
BIAS_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "confirmation": [
        re.compile(r"\bconfirm(ing|s|e)\b.+\balready\b", re.I),
        re.compile(r"\bas expected\b", re.I),
        re.compile(r"\bobviously\b", re.I),
    ],
    "anchoring": [
        re.compile(r"\bstarting from\b.+\bestimate\b", re.I),
        re.compile(r"\bbased on initial\b", re.I),
    ],
    "availability": [
        re.compile(r"\blast time\b", re.I),
        re.compile(r"\brecent case\b", re.I),
    ],
    "sunk_cost": [
        re.compile(r"\balready (spent|invested|done)\b", re.I),
        re.compile(r"\bcan'?t abandon\b", re.I),
    ],
    "overconfidence": [
        re.compile(r"\bdefinitely\b", re.I),
        re.compile(r"\b(100|99) ?%\b", re.I),
        re.compile(r"\bno doubt\b", re.I),
    ],
    "groupthink": [
        re.compile(r"\bwe all agree\b", re.I),
        re.compile(r"\bconsensus\b", re.I),
    ],
    "recency": [
        re.compile(r"\bjust (now|yesterday|today)\b", re.I),
    ],
    "halo": [
        re.compile(r"\bsince X is good\b", re.I),
        re.compile(r"\btrusted because\b", re.I),
    ],
}


# Mitigation strategies (retournees pour executeur externe)
BIAS_MITIGATIONS: dict[str, dict[str, str]] = {
    "confirmation": {
        "action": "search_contradictory_evidence",
        "prompt": "Cherche activement des preuves qui CONTREDISENT la solution."},
    "anchoring": {
        "action": "partial_reinit",
        "prompt": "Redemarre l'analyse sans l'estimation initiale."},
    "availability": {
        "action": "diversify_sources",
        "prompt": "Ajoute des sources sans lien avec les cas recents."},
    "sunk_cost": {
        "action": "forward_looking_eval",
        "prompt": "Evalue uniquement sur les couts futurs et benefices attendus."},
    "overconfidence": {
        "action": "strengthen_critic",
        "prompt": "Double la revue critique ; liste 3 ways this could fail."},
    "groupthink": {
        "action": "activate_devils_advocate",
        "prompt": "Active un contradicteur explicite pour attaquer la solution."},
    "recency": {
        "action": "rebalance_history",
        "prompt": "Repondere historique sur les 12 derniers mois, pas juste derniers jours."},
    "halo": {
        "action": "decouple_evaluations",
        "prompt": "Evalue chaque dimension independamment, sans se reposer sur reputation."},
}


@dataclass
class BiasDetection:
    name: str
    matches: list[str]


def detect(text: str, *, votes_convergence_ratio: float = 0.0) -> list[BiasDetection]:
    """Detecte biais dans un texte.
    votes_convergence_ratio : fraction de votes identiques (groupthink if > 0.9)."""
    found: list[BiasDetection] = []
    for name, patterns in BIAS_PATTERNS.items():
        hits = []
        for p in patterns:
            m = p.search(text or "")
            if m:
                hits.append(m.group(0))
        if hits:
            found.append(BiasDetection(name=name, matches=hits))
    if votes_convergence_ratio > 0.9:
        if not any(b.name == "groupthink" for b in found):
            found.append(BiasDetection(
                name="groupthink",
                matches=[f"votes_convergence={votes_convergence_ratio:.2f}"]))
    return found


def apply_mitigations(
    detections: list[BiasDetection],
) -> list[dict[str, str]]:
    """Retourne la liste des actions de mitigation a executer."""
    out: list[dict[str, str]] = []
    for d in detections:
        mit = BIAS_MITIGATIONS.get(d.name)
        if mit:
            out.append({"bias": d.name, **mit,
                        "matches": ",".join(d.matches[:3])})
    return out


def build_report(
    text: str, *, votes_convergence_ratio: float = 0.0,
) -> BiasReport:
    detections = detect(text, votes_convergence_ratio=votes_convergence_ratio)
    mitigations = apply_mitigations(detections)
    return BiasReport(
        biases_detected=[d.name for d in detections],
        mitigations_applied=mitigations,
    )
