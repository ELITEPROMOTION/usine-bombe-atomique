"""V8 OSINT module #4 — Dendani DNS audit (typosquatting detection).

Genere des permutations dnstwist-style des domaines Dendani, resolve, et
alert si des domaines proches existent (potentiel phishing).

Sources externes : DNS public uniquement (resolution standard).
Risk level : low.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import string
from dataclasses import dataclass
from typing import Any

from app.osint.legal_framework import (
    DENDANI_DOMAIN_WHITELIST,
    RiskLevel,
    dendani_only,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.dns_audit")

# Caracteres ASCII proches utilises pour generer typos.
HOMOGLYPHS = {
    "a": ["e", "o", "q", "4"],
    "e": ["a", "i", "3"],
    "i": ["1", "l", "j"],
    "l": ["1", "i"],
    "o": ["0", "Q", "p"],
    "n": ["m", "h"],
    "m": ["n", "rn"],
    "u": ["v", "y"],
    "d": ["b", "cl"],
}


def _permute_domain(domain: str, max_variants: int = 30) -> list[str]:
    """Genere des variations dnstwist-like : substitution, insertion, omission."""
    parts = domain.split(".")
    if len(parts) < 2:
        return []
    name, tld = parts[0], ".".join(parts[1:])
    out: set[str] = set()

    # Substitution caracter
    for i, ch in enumerate(name):
        for repl in HOMOGLYPHS.get(ch, []):
            v = name[:i] + repl + name[i + 1:]
            if v != name:
                out.add(f"{v}.{tld}")

    # Insertion
    for i in range(len(name) + 1):
        for c in "aeious":
            v = name[:i] + c + name[i:]
            if len(v) <= len(name) + 1:
                out.add(f"{v}.{tld}")

    # Omission
    for i in range(len(name)):
        v = name[:i] + name[i + 1:]
        if v:
            out.add(f"{v}.{tld}")

    # Doubling
    for i in range(len(name)):
        v = name[:i] + name[i] + name[i] + name[i + 1:]
        out.add(f"{v}.{tld}")

    # Bit-flip TLD heuristic (e.g. dz -> dx, da)
    if tld == "dz":
        for alt in ("dx", "da", "dn", "dc", "dr"):
            out.add(f"{name}.{alt}")

    return sorted(out)[:max_variants]


def _resolve(domain: str, timeout: float = 4.0) -> dict[str, Any]:
    socket.setdefaulttimeout(timeout)
    try:
        ips = socket.gethostbyname_ex(domain)[2]
        return {"resolves": True, "ips": ips}
    except (socket.gaierror, socket.timeout, OSError):
        return {"resolves": False}


@rate_limit_strict(max_per_hour=20)
@log_osint_action(risk_level=RiskLevel.LOW, module="dendani_dns_audit")
@dendani_only("target")
async def audit_typosquatting(target: str, max_variants: int = 30,
                               _actor: str = "scheduler",
                               _consent_id: str | None = None) -> dict[str, Any]:
    variants = _permute_domain(target, max_variants=max_variants)
    loop = asyncio.get_event_loop()
    results: list[dict[str, Any]] = []
    for v in variants:
        rep = await loop.run_in_executor(None, _resolve, v)
        if rep.get("resolves"):
            results.append({"variant": v, **rep, "alert": "typosquatting-suspect"})
    return {"target": target, "variants_tested": len(variants),
            "alerts": results, "alerts_count": len(results)}


async def audit_all_dendani_typosquats() -> list[dict[str, Any]]:
    out = []
    for d in DENDANI_DOMAIN_WHITELIST:
        try:
            out.append(await audit_typosquatting(target=d))
        except Exception as exc:
            out.append({"target": d, "error": str(exc)[:200]})
    return out


__all__ = ["audit_typosquatting", "audit_all_dendani_typosquats"]
