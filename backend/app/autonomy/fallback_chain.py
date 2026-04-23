"""V5.1 BLOC 3 - Fallback Chain.

Avant toute demande B (paiement) ou A (compte paye), on essaie une chaine
de fallbacks :
  1. Open-source equivalent (ex: SonarQube OSS au lieu de SonarCloud)
  2. Free tier existant (ex: Datadog free 5 hosts)
  3. Alternative deja en place dans le repo (bandit+radon au lieu de sonar)
  4. Defer 7 jours (accumuler evidence de valeur avant paiement)

Table de correspondance extensible :
  "datadog"      -> ["prometheus+grafana", "datadog-free-5hosts"]
  "sonarcloud"   -> ["sonarqube-oss-local", "bandit+radon"]
  "github-copilot" -> ["supermaven-free", "continue.dev-local"]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FALLBACK_MAP: dict[str, list[dict[str, Any]]] = {
    "datadog": [
        {"name": "prometheus+grafana", "kind": "open_source",
         "integration_effort": "medium", "coverage": 0.85},
        {"name": "datadog-free-5hosts", "kind": "free_tier",
         "integration_effort": "low", "coverage": 1.0, "limit": "5 hosts"},
    ],
    "sonarcloud": [
        {"name": "sonarqube-oss-local", "kind": "open_source",
         "integration_effort": "low", "coverage": 0.95},
        {"name": "bandit+radon", "kind": "in_repo",
         "integration_effort": "none", "coverage": 0.75},
    ],
    "github-copilot": [
        {"name": "supermaven-free", "kind": "free_tier",
         "integration_effort": "low", "coverage": 0.80},
        {"name": "continue.dev-local", "kind": "open_source",
         "integration_effort": "medium", "coverage": 0.85},
    ],
    "stripe": [
        {"name": "defer_7d", "kind": "defer",
         "integration_effort": "none", "coverage": 0.0,
         "note": "pas de fallback gratuit credible, temporiser"},
    ],
    "openai": [
        {"name": "anthropic-claude", "kind": "already_in_stack",
         "integration_effort": "none", "coverage": 1.0},
    ],
}


@dataclass
class FallbackDecision:
    service: str
    recommended: dict[str, Any] | None
    all_options: list[dict[str, Any]]
    should_still_ask: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service, "recommended": self.recommended,
            "all_options": self.all_options,
            "should_still_ask": self.should_still_ask, "reason": self.reason,
        }


def find(service: str, min_coverage: float = 0.70) -> FallbackDecision:
    slug = service.lower().strip()
    opts = FALLBACK_MAP.get(slug, [])
    if not opts:
        return FallbackDecision(
            service=service, recommended=None, all_options=[],
            should_still_ask=True,
            reason=f"aucun fallback connu pour {service}",
        )
    # Tri : coverage desc, puis integration low effort
    effort_rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
    sorted_opts = sorted(
        opts, key=lambda o: (
            -float(o.get("coverage", 0.0)),
            effort_rank.get(o.get("integration_effort", "medium"), 2),
        ),
    )
    best = sorted_opts[0]
    coverage = float(best.get("coverage", 0.0))
    if coverage >= min_coverage:
        return FallbackDecision(
            service=service, recommended=best, all_options=sorted_opts,
            should_still_ask=False,
            reason=f"fallback {best['name']} couvre {coverage*100:.0f}% du besoin",
        )
    return FallbackDecision(
        service=service, recommended=best, all_options=sorted_opts,
        should_still_ask=True,
        reason=(f"meilleur fallback {best['name']} a {coverage*100:.0f}% "
                f"< seuil {min_coverage*100:.0f}%"),
    )


def register(service: str, options: list[dict[str, Any]]) -> None:
    """Hook pour enrichir la map a chaud (utilise par intervention_learner)."""
    FALLBACK_MAP[service.lower().strip()] = options
