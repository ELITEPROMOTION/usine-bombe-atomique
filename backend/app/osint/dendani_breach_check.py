"""V8 OSINT module #2 — Dendani breach check (HaveIBeenPwned, dendani_only).

Verifie les emails @dendani.dz contre HIBP API v3 (free tier). PAS de check
sur emails externes (refus auto via dendani_only).

Sources externes : api.haveibeenpwned.com (Pwned Passwords / Breached Account)
Risk level : low.
"""
from __future__ import annotations

import asyncio
import hashlib
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

logger = logging.getLogger("uba.osint.breach_check")

HIBP_BASE = os.getenv("HIBP_API_BASE", "https://haveibeenpwned.com/api/v3")
PWNEDPW_BASE = os.getenv("PWNEDPW_API_BASE", "https://api.pwnedpasswords.com")


def _is_dendani_email(email: str) -> bool:
    return email.lower().strip().endswith("@dendani.dz")


@rate_limit_strict(max_per_hour=60)
@log_osint_action(risk_level=RiskLevel.LOW, module="dendani_breach_check")
async def check_email_breach(target: str, _actor: str = "scheduler",
                              _consent_id: str | None = None) -> dict[str, Any]:
    """Check si un email Dendani est dans une breach connue.

    NB : `target` ici est l'email. Refus auto si pas @dendani.dz.
    """
    if not _is_dendani_email(target):
        raise ScopeViolationError(f"breach_check refuse non-Dendani email: {target}")

    api_key = os.getenv("HIBP_API_KEY", "").strip()
    if not api_key:
        return {"target": target, "skipped": "HIBP_API_KEY not set",
                "breaches": [], "count": 0}

    headers = {
        "hibp-api-key": api_key,
        "user-agent": "UBA-V8-OSINT-Defensive",
    }
    url = f"{HIBP_BASE}/breachedaccount/{target}?truncateResponse=false"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 404:
            return {"target": target, "breaches": [], "count": 0}
        if r.status_code == 429:
            return {"target": target, "rate_limited": True,
                    "retry_after_s": int(r.headers.get("retry-after", "1"))}
        if r.status_code >= 400:
            return {"target": target, "error": f"hibp-{r.status_code}"}
        data = r.json()
    breaches = [{
        "name": b.get("Name"),
        "title": b.get("Title"),
        "domain": b.get("Domain"),
        "breach_date": b.get("BreachDate"),
        "data_classes": b.get("DataClasses", []),
    } for b in data]
    return {"target": target, "breaches": breaches, "count": len(breaches)}


@rate_limit_strict(max_per_hour=600)
@log_osint_action(risk_level=RiskLevel.MEDIUM, module="dendani_breach_check")
async def check_password_pwned(target: str, _actor: str = "scheduler",
                                _consent_id: str | None = None) -> dict[str, Any]:
    """Anonymous k-anonymity password check (no full hash leak)."""
    if not target:
        raise ScopeViolationError("password manquant")
    sha1 = hashlib.sha1(target.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{PWNEDPW_BASE}/range/{prefix}",
                             headers={"add-padding": "true"})
        if r.status_code != 200:
            return {"pwned": None, "error": f"pwnedpw-{r.status_code}"}
        for line in r.text.splitlines():
            if ":" in line:
                s, count = line.split(":", 1)
                if s.strip() == suffix:
                    return {"pwned": True, "count": int(count.strip())}
    return {"pwned": False, "count": 0}


__all__ = ["check_email_breach", "check_password_pwned"]
