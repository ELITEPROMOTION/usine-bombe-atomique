"""V8 OSINT module #8 — Regulatory watch DZ.

Consume JORADP (Journal Officiel) RSS public + DGI (Direction Generale Impots)
si dispo. Detect nouvelles lois fiscales / business avec keywords filtrants.

Sources externes : joradp.dz, dgi.dz (publiques).
Risk level : low.
"""
from __future__ import annotations

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

logger = logging.getLogger("uba.osint.regulatory_watch")


PUBLIC_FEEDS = {
    "joradp":    "https://www.joradp.dz/JRN/JRN.htm",
    "dgi_news":  "https://www.dgi.dz/actualites?format=feed&type=rss",
    "mfdgi":     "https://www.mf.gov.dz/index.php/fr/?format=feed&type=rss",
}

DEFAULT_KEYWORDS = [
    "fiscal", "fiscalite", "tva", "irg", "ibs", "tap",
    "code commerce", "code investissement", "vefa",
    "immobilier", "tourisme", "promotion immobiliere",
    "loi de finances", "decret",
]


def _filter_items(items: list[dict[str, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    out = []
    for it in items:
        text = (it.get("title", "") + " " + it.get("summary", "")).lower()
        matched = [k for k in keywords if k.lower() in text]
        if matched:
            it["matched_keywords"] = matched
            out.append(it)
    return out


@rate_limit_strict(max_per_hour=24)
@log_osint_action(risk_level=RiskLevel.LOW, module="regulatory_watch_dz")
async def fetch_jora(target: str, keywords: list[str] | None = None,
                     _actor: str = "scheduler",
                     _consent_id: str | None = None) -> dict[str, Any]:
    """target = source key or URL directe."""
    keywords = keywords or DEFAULT_KEYWORDS
    url = PUBLIC_FEEDS.get(target, target if target.startswith("http") else None)
    if not url:
        return {"error": f"unknown-source-{target}"}

    async with httpx.AsyncClient(timeout=20.0,
                                  headers={"user-agent": "UBA-V8-RegWatch"}) as client:
        try:
            r = await client.get(url, follow_redirects=True)
        except httpx.RequestError as exc:
            return {"error": str(exc)[:160]}
    if r.status_code != 200:
        return {"source": target, "error": f"http-{r.status_code}"}

    items: list[dict[str, Any]] = []
    ctype = r.headers.get("content-type", "")
    if "xml" in ctype or "rss" in ctype or r.text.lstrip().startswith("<?xml"):
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
                    items.append({"title": title, "link": link,
                                   "summary": summary[:400], "published": pub})
        except ET.ParseError:
            return {"source": target, "error": "rss-parse-fail"}
    else:
        # HTML fallback : extract rough headings
        for m in re.finditer(r"<h[1-3][^>]*>(.*?)</h[1-3]>", r.text, re.I | re.S):
            title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            if title:
                items.append({"title": title[:200]})

    matched = _filter_items(items, keywords)
    return {"source": target, "feed_url": url,
            "items_total": len(items), "matched": matched,
            "matched_count": len(matched), "keywords": keywords}


__all__ = ["fetch_jora", "PUBLIC_FEEDS", "DEFAULT_KEYWORDS"]
