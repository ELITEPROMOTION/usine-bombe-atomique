"""V8 OSINT module #11 — Threat intelligence aggregator (public).

Consume CVE NVD JSON feeds + AlienVault OTX (free tier). Filtre stack Dendani
(python, fastapi, react, postgres, redis, vault, sonarqube, nginx, etc.) et
alert si CVE critique impacte la stack.

Sources externes : nvd.nist.gov (JSON public), otx.alienvault.com (free).
Risk level : low.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from app.osint.legal_framework import (
    RiskLevel,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.threat_intel")

DENDANI_STACK_KEYWORDS = [
    "python", "fastapi", "uvicorn", "starlette", "pydantic",
    "react", "typescript", "vite", "tailwind",
    "postgresql", "postgres", "asyncpg",
    "redis", "arq",
    "vault",
    "sonarqube",
    "nginx",
    "docker",
    "anthropic",
    "alembic",
    "httpx",
]

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"
OTX_API = "https://otx.alienvault.com/api/v1/indicators"


@rate_limit_strict(max_per_hour=12)
@log_osint_action(risk_level=RiskLevel.LOW, module="threat_intel_aggregator")
async def fetch_recent_cves(target: str = "stack",
                             keywords: list[str] | None = None,
                             days: int = 1,
                             _actor: str = "scheduler",
                             _consent_id: str | None = None) -> dict[str, Any]:
    """target='stack' (default Dendani) ou keyword unique."""
    keywords = keywords or DENDANI_STACK_KEYWORDS if target == "stack" else [target]
    keyword = "|".join(keywords[:5])
    headers = {}
    api_key = os.getenv("NVD_API_KEY", "").strip()
    if api_key:
        headers["apiKey"] = api_key
    params = {
        "resultsPerPage": "20",
        "keywordSearch": keyword[:200],
    }
    async with httpx.AsyncClient(timeout=20.0, headers={"user-agent": "UBA-V8-ThreatIntel",
                                                          **headers}) as client:
        try:
            r = await client.get(NVD_API, params=params)
        except httpx.RequestError as exc:
            return {"error": str(exc)[:160]}
    if r.status_code != 200:
        return {"error": f"nvd-{r.status_code}"}
    data = r.json()
    cves = []
    for entry in data.get("vulnerabilities", []) or []:
        c = entry.get("cve", {})
        metrics = c.get("metrics", {})
        cvss = (metrics.get("cvssMetricV31") or metrics.get("cvssMetricV30") or [{}])[0]
        score = (cvss.get("cvssData") or {}).get("baseScore")
        sev = (cvss.get("cvssData") or {}).get("baseSeverity")
        descs = c.get("descriptions", [])
        en = next((d.get("value") for d in descs if d.get("lang") == "en"), "")
        cves.append({
            "id": c.get("id"),
            "published": c.get("published"),
            "score": score,
            "severity": sev,
            "summary": (en or "")[:300],
        })
    return {"keywords": keywords, "cves": cves, "cve_count": len(cves)}


@rate_limit_strict(max_per_hour=12)
@log_osint_action(risk_level=RiskLevel.LOW, module="threat_intel_aggregator")
async def fetch_otx_pulses(target: str, _actor: str = "scheduler",
                            _consent_id: str | None = None) -> dict[str, Any]:
    """target = indicator (domain/IP/file hash)."""
    api_key = os.getenv("OTX_API_KEY", "").strip()
    if not api_key:
        return {"target": target, "skipped": "OTX_API_KEY not set"}
    indicator_type = "domain" if "." in target and not target.replace(".", "").isdigit() else "IPv4"
    url = f"{OTX_API}/{indicator_type}/{target}/general"
    async with httpx.AsyncClient(timeout=15.0,
                                  headers={"x-otx-api-key": api_key,
                                            "user-agent": "UBA-V8-OTX"}) as client:
        r = await client.get(url)
    if r.status_code != 200:
        return {"target": target, "error": f"otx-{r.status_code}"}
    data = r.json()
    return {
        "target": target,
        "type": indicator_type,
        "pulse_count": data.get("pulse_info", {}).get("count", 0),
        "tags": data.get("pulse_info", {}).get("references", [])[:10],
        "validation": data.get("validation", []),
    }


__all__ = ["fetch_recent_cves", "fetch_otx_pulses", "DENDANI_STACK_KEYWORDS"]
