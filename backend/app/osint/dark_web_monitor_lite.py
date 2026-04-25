"""V8 OSINT module #12 — Dark web monitor lite (LEGAL ONLY).

PAS de scraping de marketplaces illegales. Uniquement APIs commerciales legales :
  * HIBP enterprise (paid, optional)
  * Spycloud (free tier, optional)

@dendani_only sur tous les checks. Toute tentative d'aggreger des donnees
illegales (forums clandestins, etc.) est refusee techniquement.

Sources externes : HIBP enterprise API, Spycloud API.
Risk level : medium.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from app.osint.legal_framework import (
    RiskLevel,
    ScopeViolationError,
    dendani_only,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.darkweb_lite")


# Domaines hardcoded — ce module ne fait QUE des verifs Dendani.
DENDANI_EMAIL_DOMAINS = ("dendani.dz",)


def _is_dendani_email(email: str) -> bool:
    return any(email.lower().endswith("@" + d) for d in DENDANI_EMAIL_DOMAINS)


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dark_web_monitor_lite")
@dendani_only("target")
async def hibp_enterprise_lookup(target: str, _actor: str = "scheduler",
                                  _consent_id: str | None = None) -> dict[str, Any]:
    """target = domaine Dendani. Liste les breaches du domaine via HIBP enterprise."""
    api_key = os.getenv("HIBP_ENTERPRISE_API_KEY", "").strip()
    if not api_key:
        return {"target": target, "skipped": "HIBP_ENTERPRISE_API_KEY not set"}
    url = f"https://haveibeenpwned.com/api/v3/breaches?domain={target}"
    async with httpx.AsyncClient(timeout=20.0,
                                  headers={"hibp-api-key": api_key,
                                            "user-agent": "UBA-V8-DarkWebMon"}) as client:
        r = await client.get(url)
    if r.status_code != 200:
        return {"target": target, "error": f"hibp-{r.status_code}"}
    data = r.json()
    return {"target": target, "breaches": [{"name": b.get("Name"),
                                              "title": b.get("Title"),
                                              "date": b.get("BreachDate"),
                                              "pwn_count": b.get("PwnCount"),
                                              "data_classes": b.get("DataClasses", [])}
                                             for b in data],
            "count": len(data)}


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dark_web_monitor_lite")
@dendani_only("target")
async def spycloud_lookup(target: str, _actor: str = "scheduler",
                           _consent_id: str | None = None) -> dict[str, Any]:
    """target = domaine Dendani. Spycloud lookup (free tier scaffold)."""
    api_key = os.getenv("SPYCLOUD_API_KEY", "").strip()
    if not api_key:
        return {"target": target, "skipped": "SPYCLOUD_API_KEY not set"}
    # Endpoint Spycloud reel : /v2/breach/data/domains/{domain}
    url = f"https://api.spycloud.com/v2/breach/data/domains/{target}"
    async with httpx.AsyncClient(timeout=20.0,
                                  headers={"x-api-key": api_key,
                                            "user-agent": "UBA-V8-DarkWebMon"}) as client:
        r = await client.get(url)
    if r.status_code == 401:
        return {"target": target, "error": "spycloud-auth-failed"}
    if r.status_code == 404:
        return {"target": target, "no-breach-found": True}
    if r.status_code != 200:
        return {"target": target, "error": f"spycloud-{r.status_code}"}
    data = r.json()
    return {"target": target,
            "results": (data.get("results") or [])[:50],
            "count": len(data.get("results") or [])}


@log_osint_action(risk_level=RiskLevel.CRITICAL, module="dark_web_monitor_lite")
async def attempt_marketplace_scrape(target: str, _actor: str = "system",
                                       _consent_id: str | None = None) -> dict[str, Any]:
    """REFUS TECHNIQUE : ce module n'aggrege jamais des sources illegales.

    Existe uniquement pour rendre explicite (et auditer) toute tentative.
    """
    raise ScopeViolationError(
        "marketplace scraping refused : illegal under DZ 09-04 + RGPD. "
        "Use legal commercial APIs (HIBP enterprise, Spycloud) instead."
    )


__all__ = ["hibp_enterprise_lookup", "spycloud_lookup", "attempt_marketplace_scrape"]
