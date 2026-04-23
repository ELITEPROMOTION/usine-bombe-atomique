"""V5.4 - Frontier Knowledge.

Liste des sources (metadata). Fetch reel offline en V1 ; structure prete.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FrontierSource:
    name: str
    url: str
    tier: int
    domain: str


FRONTIER_SOURCES: list[FrontierSource] = [
    FrontierSource("arxiv", "https://arxiv.org/list/cs.AI/recent", 2, "research"),
    FrontierSource("openreview", "https://openreview.net/", 2, "research"),
    FrontierSource("anthropic_research", "https://www.anthropic.com/research", 1, "ai_frontier"),
    FrontierSource("deepmind", "https://deepmind.google/discover/", 1, "ai_frontier"),
    FrontierSource("openai_research", "https://openai.com/research", 1, "ai_frontier"),
    FrontierSource("meta_ai", "https://ai.meta.com/research/", 2, "ai_frontier"),
    FrontierSource("google_research", "https://research.google/", 2, "ai_frontier"),
]


def by_domain(domain: str) -> list[FrontierSource]:
    return [s for s in FRONTIER_SOURCES if s.domain == domain]


def catalog() -> dict[str, Any]:
    return {
        "total": len(FRONTIER_SOURCES),
        "by_tier": {t: sum(1 for s in FRONTIER_SOURCES if s.tier == t)
                     for t in (1, 2, 3)},
        "sources": [s.__dict__ for s in FRONTIER_SOURCES],
    }


def relevance_score(keywords: list[str], source_name: str) -> float:
    """V1 : score deterministe basique."""
    base = 0.5
    if source_name in ("anthropic_research", "deepmind", "openai_research"):
        base += 0.2
    if any(k.lower() in ("reasoning", "chain", "thought", "mcts")
           for k in keywords):
        base += 0.1
    return min(1.0, base)
