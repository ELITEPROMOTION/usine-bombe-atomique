"""V8 OSINT module #5 — Dendani brand monitoring (public sources).

Aggrege Google Alerts RSS + Reddit JSON (public). Recherche mentions de
"Dendani". Sentiment analysis basique (heuristic keyword scoring).

Sources externes : feedburner / reddit.com/search.json (public, no auth).
Risk level : low.
"""
from __future__ import annotations

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.osint.legal_framework import (
    RiskLevel,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.brand_monitor")


POSITIVE_WORDS = {
    "bon", "bonne", "excellent", "top", "qualite", "rapide", "fiable",
    "satisfait", "recommande", "professionnel", "moderne", "innovant",
    "good", "great", "best", "love", "recommend",
}
NEGATIVE_WORDS = {
    "mauvais", "lent", "cher", "scandale", "arnaque", "deception",
    "probleme", "bug", "lent", "bad", "worst", "scam", "fraud", "complaint",
}


def _sentiment(text: str) -> str:
    t = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    neg = sum(1 for w in NEGATIVE_WORDS if re.search(rf"\b{re.escape(w)}\b", t))
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


@rate_limit_strict(max_per_hour=12)
@log_osint_action(risk_level=RiskLevel.LOW, module="dendani_brand_monitor")
async def fetch_rss(target: str, _actor: str = "scheduler",
                     _consent_id: str | None = None) -> dict[str, Any]:
    """target = URL RSS feed (Google Alerts, etc.). Public source only."""
    if not target.startswith(("http://", "https://")):
        return {"error": "rss-url-required"}
    async with httpx.AsyncClient(timeout=15.0,
                                  headers={"user-agent": "UBA-V8-Monitor"}) as client:
        r = await client.get(target)
    if r.status_code != 200:
        return {"error": f"http-{r.status_code}"}
    items: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(r.text)
        # Atom or RSS 2.0
        for entry in root.iter():
            tag = entry.tag.lower()
            if tag.endswith("entry") or tag.endswith("item"):
                title = ""
                link = ""
                summary = ""
                published = ""
                for c in entry:
                    ctag = c.tag.lower().rsplit("}", 1)[-1]
                    if ctag == "title":
                        title = (c.text or "").strip()
                    elif ctag == "link":
                        link = c.attrib.get("href") or (c.text or "").strip()
                    elif ctag in ("summary", "description"):
                        summary = (c.text or "").strip()
                    elif ctag in ("published", "pubdate"):
                        published = (c.text or "").strip()
                items.append({
                    "title": title, "link": link,
                    "summary": summary[:400],
                    "published": published,
                    "sentiment": _sentiment(title + " " + summary),
                })
    except ET.ParseError:
        return {"error": "rss-parse-fail"}
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for it in items:
        counts[it["sentiment"]] = counts.get(it["sentiment"], 0) + 1
    return {"source": target, "items": items[:50],
            "items_count": len(items), "sentiment_counts": counts}


@rate_limit_strict(max_per_hour=24)
@log_osint_action(risk_level=RiskLevel.LOW, module="dendani_brand_monitor")
async def fetch_reddit_mentions(target: str, _actor: str = "scheduler",
                                 _consent_id: str | None = None) -> dict[str, Any]:
    """target = mot-cle (ex: 'dendani'). Reddit search JSON public."""
    if not target or len(target) > 100:
        return {"error": "invalid-keyword"}
    url = f"https://www.reddit.com/search.json?q={target}&limit=25&sort=new"
    async with httpx.AsyncClient(timeout=15.0,
                                  headers={"user-agent": "UBA-V8-Monitor"}) as client:
        r = await client.get(url)
    if r.status_code != 200:
        return {"error": f"reddit-{r.status_code}"}
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    posts = []
    for child in (data.get("data") or {}).get("children", []) or []:
        d = child.get("data") or {}
        title = d.get("title", "")
        body = d.get("selftext", "")[:500]
        posts.append({
            "title": title, "subreddit": d.get("subreddit"),
            "url": "https://reddit.com" + (d.get("permalink") or ""),
            "score": d.get("score"),
            "created_utc": d.get("created_utc"),
            "sentiment": _sentiment(title + " " + body),
        })
    return {"source": "reddit", "keyword": target,
            "posts": posts, "posts_count": len(posts)}


__all__ = ["fetch_rss", "fetch_reddit_mentions"]
