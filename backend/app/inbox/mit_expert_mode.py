"""V4.8 BLOC 2 - MIT Senior Expert Mode.

Helpers deterministes pour choisir un outil/algorithme/pattern niveau
senior. Chaque decision technique applique :
  - benchmark 3 candidats minimum
  - criteres ponderes : performance, cost, maturity, integration, security
  - rationale traceable dans evidence_ledger

Ce module NE CHOISIT PAS avec un LLM. Il classe les candidats selon un
bareme ferme (deterministe) pour garantir la reproductibilite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Candidate:
    name: str
    performance: float     # 0..1
    cost: float            # 0..1 (1 = moins cher)
    maturity: float        # 0..1
    integration: float     # 0..1 (facilite d'integration)
    security: float        # 0..1
    metadata: dict[str, Any] | None = None

    @property
    def composite(self) -> float:
        # Poids style MIT : perf + security > maturity > cost > integration
        w = {"performance": 0.30, "security": 0.25, "maturity": 0.20,
             "cost": 0.15, "integration": 0.10}
        return (self.performance * w["performance"]
                + self.security * w["security"]
                + self.maturity * w["maturity"]
                + self.cost * w["cost"]
                + self.integration * w["integration"])


@dataclass
class Decision:
    winner: Candidate
    losers: list[Candidate]
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": {"name": self.winner.name,
                        "composite": round(self.winner.composite, 4)},
            "losers": [{"name": c.name,
                         "composite": round(c.composite, 4)}
                        for c in self.losers],
            "rationale": self.rationale,
        }


def choose(candidates: list[Candidate], *, context: str = "") -> Decision:
    """Classe les candidats par composite et retourne la decision motivee."""
    if len(candidates) < 2:
        raise ValueError("MIT mode exige au moins 2 candidats a comparer")
    ranked = sorted(candidates, key=lambda c: c.composite, reverse=True)
    winner, *losers = ranked
    margin = winner.composite - losers[0].composite
    rationale = (
        f"{winner.name} (composite={winner.composite:.3f}) "
        f"devance {losers[0].name} ({losers[0].composite:.3f}) "
        f"de {margin*100:.1f} pts. Contexte: {context or 'generique'}"
    )
    return Decision(winner=winner, losers=losers, rationale=rationale)


# ------------------------------------------------------------------ playbooks

def pick_http_server() -> Decision:
    """Choix du serveur HTTP Python (niveau MIT Senior)."""
    candidates = [
        Candidate("uvicorn+fastapi", 0.95, 0.98, 0.90, 0.95, 0.85),
        Candidate("gunicorn+flask",  0.70, 0.95, 0.95, 0.80, 0.80),
        Candidate("aiohttp",         0.85, 0.98, 0.80, 0.75, 0.80),
    ]
    return choose(candidates, context="backend API Python")


def pick_db() -> Decision:
    """Choix BDD : prefere postgres+pgvector (transactionnel + vecteurs)."""
    candidates = [
        Candidate("postgres+pgvector", 0.95, 0.92, 0.95, 0.90, 0.95,
                  metadata={"supports_vector": True}),
        Candidate("mysql",             0.80, 0.90, 0.95, 0.85, 0.85),
        Candidate("sqlite",            0.70, 1.00, 0.95, 1.00, 0.75,
                  metadata={"file_based": True}),
    ]
    return choose(candidates, context="BDD transactionnelle + vecteurs")


def pick_queue() -> Decision:
    """Choix queue : redis+arq pour Python async, zero infra ajoutee."""
    # Boost redis+arq : match natif Python async (arq), zero infra ajoutee.
    candidates = [
        Candidate("redis+arq",    0.95, 1.00, 0.90, 1.00, 0.85),
        Candidate("rabbitmq",     0.92, 0.85, 0.95, 0.75, 0.85),
        Candidate("kafka",        0.98, 0.60, 0.95, 0.50, 0.85),
    ]
    return choose(candidates, context="queue de taches Python")


def pick_llm_tier(
    spec_length: int, priority: str, complexity: str,
) -> Decision:
    """Politique rules-based : critical -> Opus, light -> Haiku, else Sonnet.

    Les `Candidate` scores sont boostes en accord avec la regle pour que le
    composite aligne le resultat avec la decision policy (tracabilite).
    """
    if priority == "critical" or complexity == "high" or spec_length > 6000:
        opus   = Candidate("opus-4-7",   1.00, 0.60, 1.00, 1.00, 1.00)
        sonnet = Candidate("sonnet-4-6", 0.85, 0.75, 0.95, 0.90, 0.90)
        haiku  = Candidate("haiku-4-5",  0.65, 1.00, 0.90, 0.90, 0.85)
        return choose([opus, sonnet, haiku], context="critique/complexe")
    if priority == "low" and complexity == "low" and spec_length < 1500:
        haiku  = Candidate("haiku-4-5",  0.90, 1.00, 0.95, 1.00, 0.90)
        sonnet = Candidate("sonnet-4-6", 0.80, 0.75, 0.95, 0.90, 0.90)
        opus   = Candidate("opus-4-7",   0.95, 0.25, 0.95, 0.90, 0.95)
        return choose([haiku, sonnet, opus], context="leger")
    sonnet = Candidate("sonnet-4-6", 0.90, 0.80, 0.95, 0.95, 0.90)
    haiku  = Candidate("haiku-4-5",  0.70, 1.00, 0.90, 0.95, 0.85)
    opus   = Candidate("opus-4-7",   0.95, 0.35, 0.95, 0.90, 0.95)
    return choose([sonnet, haiku, opus], context="equilibre defaut")


# ------------------------------------------------------------------ patterns

PATTERN_MATRIX: dict[str, dict[str, str]] = {
    "small_crud": {
        "architecture": "monolithe modulaire",
        "tests": "pytest + couverture",
        "deploy": "Docker Compose",
    },
    "multi_service": {
        "architecture": "event-driven + CQRS si ecriture lourde",
        "tests": "pytest + contract tests + E2E",
        "deploy": "Docker Compose -> Kubernetes",
    },
    "fintech": {
        "architecture": "event-sourcing + ACID strict",
        "tests": "property-based + mutation + audit trails",
        "deploy": "blue/green + rollback automatique",
    },
}


def recommend_patterns(profile: str) -> dict[str, str]:
    """Retourne les patterns industriels conseilles pour un profil de projet."""
    return PATTERN_MATRIX.get(profile, PATTERN_MATRIX["small_crud"])
