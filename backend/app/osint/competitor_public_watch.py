"""V8 OSINT module #6 — Competitor public watch (RSS DZ news).

Aggrege flux RSS publics : Algerie-Eco, TSA, El-Watan, Liberte. Filtre
keywords concurrents. Pas de scraping derriere paywall, pas d'enrichissement
personnel : sources publiques uniquement.

Sources externes : RSS publiques news DZ.
Risk level : low.
"""
from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.osint.legal_framework import (
    RiskLevel,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.competitor_watch")


DEFAULT_FEEDS = {
    "algerie_eco": "https://www.algerie-eco.com/feed/",
    "tsa_algerie": "https://www.tsa-algerie.com/feed/",
    "elwatan":      "https://www.elwatan.com/rss",
    "liberte":      "https://www.liberte-algerie.com/rss",
}


def _matches_any(text: str, keywords: list[str]) -> list[str]:
    t = text.lower()
    return [k for k in keywords if k.lower() in t]


@rate_limit_strict(max_per_hour=24)
@log_osint_action(risk_level=RiskLevel.LOW, module="competitor_public_watch")
async def fetch_competitor_news(target: str, keywords: list[str] | None = None,
                                 _actor: str = "scheduler",
                                 _consent_id: str | None = None) -> dict[str, Any]:
    """target = nom du flux dans DEFAULT_FEEDS ou URL RSS direct."""
    keywords = keywords or []
    url = DEFAULT_FEEDS.get(target, target if target.startswith("http") else None)
    if not url:
        return {"error": f"unknown-feed-{target}"}
    async with httpx.AsyncClient(timeout=15.0,
                                  headers={"user-agent": "UBA-V8-CompetitorWatch"}) as client:
        try:
            r = await client.get(url)
        except httpx.RequestError as exc:
            return {"error": f"http-error: {str(exc)[:160]}"}
    if r.status_code != 200:
        return {"error": f"http-{r.status_code}"}

    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        for entry in root.iter():
            tag = entry.tag.lower().rsplit("}", 1)[-1]
            if tag in ("entry", "item"):
                title = ""
                link = ""
                summary = ""
                pub = ""
                for c in entry:
                    ctag = c.tag.lower().rsplit("}", 1)[-1]
                    if ctag == "title":
                        title = (c.text or "").strip()
                    elif ctag == "link":
                        link = c.attrib.get("href") or (c.text or "").strip()
                    elif ctag in ("summary", "description"):
                        summary = (c.text or "").strip()
                    elif ctag in ("published", "pubdate"):
                        pub = (c.text or "").strip()
                matched = _matches_any(title + " " + summary, keywords) if keywords else []
                if not keywords or matched:
                    items.append({"title": title, "link": link,
                                   "summary": summary[:400],
                                   "published": pub, "matched_keywords": matched})
    except ET.ParseError:
        return {"error": "rss-parse-fail"}

    return {"source": target, "feed_url": url,
            "items": items[:50], "items_count": len(items),
            "keywords_filter": keywords}


@log_osint_action(risk_level=RiskLevel.LOW, module="competitor_public_watch")
async def aggregate_all(target: str = "all", keywords: list[str] | None = None,
                         _actor: str = "scheduler",
                         _consent_id: str | None = None) -> dict[str, Any]:
    out = {}
    for name in DEFAULT_FEEDS:
        try:
            out[name] = await fetch_competitor_news(target=name, keywords=keywords,
                                                     _actor=_actor)
        except Exception as exc:
            out[name] = {"error": str(exc)[:200]}
    return out


__all__ = ["fetch_competitor_news", "aggregate_all", "DEFAULT_FEEDS"]
