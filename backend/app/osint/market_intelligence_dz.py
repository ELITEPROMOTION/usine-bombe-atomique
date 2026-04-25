"""V8 OSINT module #7 — Market intelligence DZ.

Consume APIs/datasets PUBLICS : ONS DZ (Office National Statistiques), Banque
d'Algerie. Tendances economiques + indicateurs sectoriels.

Sources externes : ons.dz, bank-of-algeria.dz (publiques).
Risk level : low.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.osint.legal_framework import (
    RiskLevel,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.market_intel_dz")


PUBLIC_SOURCES = {
    "ons_dz_indicators":  "https://www.ons.dz/spip.php?rubrique56",
    "bank_algeria_rates": "https://www.bank-of-algeria.dz/wp-json/wp/v2/posts?per_page=20",
    "jobs_dz":            "https://www.algerie-tomtom.com/feed",
}

SECTOR_KEYWORDS = {
    "immobilier": ["immobilier", "logement", "vefa", "promotion immobiliere"],
    "btp":        ["btp", "construction", "ciment", "infrastructure"],
    "hotellerie": ["hotel", "hotellerie", "tourisme", "residences"],
    "fiscal":     ["fiscal", "fiscalite", "irg", "ibs", "tva", "impot"],
}


@rate_limit_strict(max_per_hour=12)
@log_osint_action(risk_level=RiskLevel.LOW, module="market_intelligence_dz")
async def fetch_public_indicator(target: str, _actor: str = "scheduler",
                                  _consent_id: str | None = None) -> dict[str, Any]:
    """target = key dans PUBLIC_SOURCES ou URL directe."""
    url = PUBLIC_SOURCES.get(target, target if target.startswith("http") else None)
    if not url:
        return {"error": f"unknown-source-{target}"}
    async with httpx.AsyncClient(timeout=20.0,
                                  headers={"user-agent": "UBA-V8-MarketIntel"}) as client:
        try:
            r = await client.get(url, follow_redirects=True)
        except httpx.RequestError as exc:
            return {"error": str(exc)[:160]}
    return {"source": target, "url": url, "status": r.status_code,
            "size_bytes": len(r.content),
            "content_type": r.headers.get("content-type", "?"),
            "preview": r.text[:1000] if r.text else None}


@log_osint_action(risk_level=RiskLevel.LOW, module="market_intelligence_dz")
async def aggregate_sector_signals(target: str = "all",
                                    _actor: str = "scheduler",
                                    _consent_id: str | None = None) -> dict[str, Any]:
    """target = sector key or 'all'."""
    sectors = list(SECTOR_KEYWORDS.keys()) if target == "all" else [target]
    out = {}
    for s in sectors:
        if s not in SECTOR_KEYWORDS:
            continue
        out[s] = {"keywords": SECTOR_KEYWORDS[s], "sources_polled": []}
        for src_name in ("ons_dz_indicators", "bank_algeria_rates"):
            try:
                ind = await fetch_public_indicator(target=src_name)
                out[s]["sources_polled"].append({"source": src_name, "status": ind.get("status")})
            except Exception as exc:
                out[s]["sources_polled"].append({"source": src_name, "error": str(exc)[:120]})
    return out


__all__ = ["fetch_public_indicator", "aggregate_sector_signals",
           "PUBLIC_SOURCES", "SECTOR_KEYWORDS"]
