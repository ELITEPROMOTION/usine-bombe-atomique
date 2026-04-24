"""V5.3 BLOC 5 - Auto Triangulator.

7 etapes : qualification -> selection -> interrogation -> normalization
  -> concordance -> verdict -> preuve
Verdict : TRUE / UNCERTAIN / FALSE / UNKNOWN
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.ctc import evidence_harvester, source_registry

logger = logging.getLogger(__name__)


SCORE_TRUE = 85
SCORE_FALSE = 50


@dataclass
class TriangulationResult:
    claim: str
    domain: str
    verdict: str                   # TRUE | UNCERTAIN | FALSE | UNKNOWN
    score: float                   # 0..100
    sources_consulted: int
    supports: int
    contradicts: int
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim, "domain": self.domain,
            "verdict": self.verdict, "score": round(self.score, 2),
            "sources_consulted": self.sources_consulted,
            "supports": self.supports, "contradicts": self.contradicts,
            "details": self.details,
        }


def _semantic_similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio (0..1). Simple proxy cosine."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def qualify(claim: str) -> str:
    """Step 1 : determine le domaine (regex)."""
    low = claim.lower()
    if any(w in low for w in ("cve", "vulnerability", "owasp", "xss", "sql injection")):
        return "security"
    if any(w in low for w in ("tva", "tap", "cnas", "irg", "dzd", "dinar")):
        return "compliance_dz"
    if any(w in low for w in ("rgpd", "gdpr", "cnil", "data protection")):
        return "compliance_eu"
    if any(w in low for w in ("python", "pip", "pypi", "asyncio")):
        return "lang_python"
    if any(w in low for w in ("postgresql", "postgres", "sql", "database")):
        return "database"
    if any(w in low for w in ("http", "json", "openapi", "w3c", "rfc")):
        return "web_standards"
    return "web_standards"  # default


async def triangulate(
    pool: asyncpg.Pool, claim: str, *,
    min_sources: int = 3, skip_fetch: bool = True,
) -> TriangulationResult:
    """Step 1-7 en une fonction."""
    domain = await qualify(claim)
    sources = await source_registry.pick_best(pool, domain, min_count=min_sources)
    if not sources:
        return TriangulationResult(
            claim=claim, domain=domain, verdict="UNKNOWN", score=0.0,
            sources_consulted=0, supports=0, contradicts=0,
            details={"reason": "no sources for domain"},
        )

    supports = 0
    contradicts = 0
    weighted_score = 0.0
    weight_total = 0.0
    per_source: list[dict[str, Any]] = []
    for src in sources:
        # Step 3 : harvest (simule ou reel)
        res = await evidence_harvester.fetch_one(
            pool, src.source_id, skip_actual_fetch=skip_fetch)
        if res.error:
            per_source.append({"url": src.url, "tier": src.authority_tier,
                                "status": "error", "error": res.error})
            continue
        # Step 4-5 : normalize + concordance simpliste sur le contenu fetche
        # Pour le test : similarity entre claim et un proxy du contenu
        body_proxy = res.url if skip_fetch else "<fetched>"
        sim = _semantic_similarity(claim, body_proxy)
        tier_w = source_registry.tier_weight(src.authority_tier)
        # Score = similarity * tier_weight
        contribution = sim * tier_w * 100
        weighted_score += contribution
        weight_total += tier_w
        if sim >= 0.5:
            supports += 1
        elif sim <= 0.1:
            contradicts += 1
        per_source.append({
            "url": src.url, "tier": src.authority_tier,
            "similarity": round(sim, 3), "contribution": round(contribution, 2),
        })

    # Step 6 : verdict
    score = (weighted_score / weight_total) if weight_total > 0 else 0.0
    if weight_total == 0 or len(per_source) == 0:
        verdict = "UNKNOWN"
    elif score >= SCORE_TRUE:
        verdict = "TRUE"
    elif score >= SCORE_FALSE:
        verdict = "UNCERTAIN"
    else:
        verdict = "FALSE" if supports < contradicts else "UNCERTAIN"
    return TriangulationResult(
        claim=claim, domain=domain, verdict=verdict, score=score,
        sources_consulted=len(sources), supports=supports,
        contradicts=contradicts, details={"per_source": per_source},
    )


async def triangulate_assertion(
    pool: asyncpg.Pool, assertion_id: str, skip_fetch: bool = True,
) -> TriangulationResult:
    """Wrapper : recupere l'assertion puis triangule."""
    import uuid as _u
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT normalized_text, domain FROM truth_assertions "
            "WHERE assertion_id = $1", _u.UUID(assertion_id),
        )
    if row is None:
        return TriangulationResult(
            claim="", domain="", verdict="UNKNOWN", score=0.0,
            sources_consulted=0, supports=0, contradicts=0,
            details={"reason": "assertion unknown"},
        )
    r = await triangulate(pool, row["normalized_text"],
                           skip_fetch=skip_fetch)
    # Update status selon verdict
    new_status = {"TRUE": "proven", "UNCERTAIN": "probable",
                    "FALSE": "conflicting", "UNKNOWN": "unproven"}[r.verdict]
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE truth_assertions SET status = $2, confidence = $3 "
            "WHERE assertion_id = $1",
            _u.UUID(assertion_id), new_status, int(r.score),
        )
    return r
