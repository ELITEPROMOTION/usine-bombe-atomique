"""Upgrade 12 - Selecteur d'outils dynamique.

Choix priorise selon la hierarchie V4 :
  API native > SDK officiel > CLI officielle > Protocole standard (MCP/OAS) >
  Browser automation (Playwright)

Pour chaque besoin identifie (analyse qualite, monitoring, paiement, mailing,
storage...), retourne une recommandation `ToolRecommendation` avec :
- besoin, candidats (ordonnes), choisi, integration_preferred, pourquoi.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolCandidate:
    tool_id: str
    name: str
    integration_kind: str   # api | sdk | cli | mcp | browser
    cost_tier: str          # free | free_tier | paid
    self_hostable: bool
    requires_user_input: bool


@dataclass
class ToolRecommendation:
    need: str
    candidates: list[ToolCandidate]
    chosen: ToolCandidate | None
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "need": self.need, "rationale": self.rationale,
            "chosen": _tc_dict(self.chosen) if self.chosen else None,
            "candidates": [_tc_dict(c) for c in self.candidates],
        }


def _tc_dict(c: ToolCandidate) -> dict[str, Any]:
    return {
        "tool_id": c.tool_id, "name": c.name,
        "integration_kind": c.integration_kind,
        "cost_tier": c.cost_tier, "self_hostable": c.self_hostable,
        "requires_user_input": c.requires_user_input,
    }


CATALOG: dict[str, list[ToolCandidate]] = {
    "code_quality": [
        ToolCandidate("sonarqube_ce", "SonarQube CE", "api", "free", True, False),
        ToolCandidate("sonarcloud", "SonarCloud", "api", "free_tier", False, True),
        ToolCandidate("codeclimate", "Code Climate", "api", "paid", False, True),
    ],
    "monitoring": [
        ToolCandidate("prometheus", "Prometheus", "api", "free", True, False),
        ToolCandidate("datadog", "Datadog", "api", "paid", False, True),
        ToolCandidate("newrelic", "New Relic", "api", "paid", False, True),
    ],
    "secrets": [
        ToolCandidate("vault", "HashiCorp Vault", "api", "free", True, False),
        ToolCandidate("aws_secretsmanager", "AWS Secrets Manager", "api", "paid", False, True),
    ],
    "database": [
        ToolCandidate("postgres", "PostgreSQL", "api", "free", True, False),
        ToolCandidate("supabase", "Supabase", "api", "free_tier", False, True),
    ],
    "payments": [
        ToolCandidate("stripe", "Stripe", "api", "paid", False, True),
        ToolCandidate("paypal", "PayPal", "api", "paid", False, True),
    ],
    "email": [
        ToolCandidate("smtp_local", "SMTP local (maildev)", "api", "free", True, False),
        ToolCandidate("sendgrid", "SendGrid", "api", "free_tier", False, True),
        ToolCandidate("mailgun", "Mailgun", "api", "free_tier", False, True),
    ],
    "ci_cd": [
        ToolCandidate("github_actions", "GitHub Actions", "api", "free_tier", False, True),
        ToolCandidate("gitlab_ci", "GitLab CI", "api", "free_tier", True, True),
    ],
    "hosting": [
        ToolCandidate("docker_local", "Docker Local", "cli", "free", True, False),
        ToolCandidate("vercel", "Vercel", "api", "free_tier", False, True),
        ToolCandidate("netlify", "Netlify", "api", "free_tier", False, True),
    ],
    "llm": [
        ToolCandidate("anthropic", "Anthropic Claude", "api", "paid", False, True),
        ToolCandidate("openai", "OpenAI", "api", "paid", False, True),
    ],
}


_INTEGRATION_RANK = {"api": 0, "sdk": 1, "cli": 2, "mcp": 3, "browser": 4}


def _choose(candidates: list[ToolCandidate]) -> ToolCandidate | None:
    """Priorite : self-hostable + free + integration API > ... > browser."""
    if not candidates:
        return None
    def key(c: ToolCandidate):
        cost_rank = {"free": 0, "free_tier": 1, "paid": 2}.get(c.cost_tier, 3)
        return (
            not c.self_hostable,                 # self_hostable first
            cost_rank,                           # free first
            _INTEGRATION_RANK.get(c.integration_kind, 9),
            c.requires_user_input,               # no user input preferred
        )
    return sorted(candidates, key=key)[0]


def recommend(need: str) -> ToolRecommendation:
    candidates = CATALOG.get(need, [])
    chosen = _choose(candidates)
    if chosen is None:
        return ToolRecommendation(
            need=need, candidates=[], chosen=None,
            rationale=f"Aucun candidat connu pour need='{need}'. "
                       "Ajouter une entree dans CATALOG ou demander a l'utilisateur.",
        )
    reasons = []
    if chosen.self_hostable:
        reasons.append("self-hostable")
    if chosen.cost_tier == "free":
        reasons.append("free")
    reasons.append(f"integration {chosen.integration_kind}")
    if not chosen.requires_user_input:
        reasons.append("zero user input")
    rationale = f"{chosen.name} : " + ", ".join(reasons)
    return ToolRecommendation(need=need, candidates=candidates,
                               chosen=chosen, rationale=rationale)


def recommend_many(needs: list[str]) -> list[ToolRecommendation]:
    return [recommend(n) for n in needs]
