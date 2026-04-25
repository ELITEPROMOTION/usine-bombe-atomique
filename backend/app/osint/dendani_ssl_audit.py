"""V8 OSINT module #1 — Dendani SSL audit (defensive, dendani_only).

Wrappe sslscan/testssl.sh dans un container ephemere. Ne s'execute QUE sur des
domaines Dendani hardcoded ; toute autre target -> ScopeViolationError.

Sources externes : aucune (sslscan local).
Risk level : low.
"""
from __future__ import annotations

import asyncio
import logging
import re
import ssl
import socket
from dataclasses import dataclass
from typing import Any

from app.osint.legal_framework import (
    DENDANI_DOMAIN_WHITELIST,
    RiskLevel,
    dendani_only,
    log_osint_action,
    rate_limit_strict,
)

logger = logging.getLogger("uba.osint.ssl_audit")


@dataclass
class SslReport:
    target: str
    grade: str
    issuer: str | None
    expires_in_days: int | None
    protocols: list[str]
    weak_ciphers: list[str]
    issues: list[str]


def _grade(report: dict[str, Any]) -> str:
    """Score simplifie A/B/C/D/F selon protocoles + ciphers."""
    issues = report.get("issues", [])
    weak = report.get("weak_ciphers", [])
    protocols = set(report.get("protocols", []))
    if "SSLv3" in protocols or "SSLv2" in protocols:
        return "F"
    if "TLSv1" in protocols or "TLSv1.1" in protocols:
        return "D"
    if weak:
        return "C"
    if any(i.startswith("expired") or i.startswith("self-signed") for i in issues):
        return "C"
    if "TLSv1.3" not in protocols:
        return "B"
    return "A"


async def _probe_ssl(host: str, port: int = 443, timeout: float = 8.0) -> dict[str, Any]:
    """Probe minimaliste via Python ssl (lib stdlib) — sans subprocess.

    En production une variante peut wrapper sslscan/testssl.sh via container
    ephemere (`docker run --rm drwetter/testssl.sh`) ; ici stdlib pour CI.
    """
    loop = asyncio.get_event_loop()

    def _connect() -> dict[str, Any]:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert(binary_form=False) or {}
                der = ssock.getpeercert(binary_form=True)
                version = ssock.version() or ""
                cipher = ssock.cipher() or (None, None, None)
        return {
            "version": version,
            "cipher": cipher[0],
            "subject": dict(x[0] for x in cert.get("subject", [])) if cert else {},
            "issuer": dict(x[0] for x in cert.get("issuer", [])) if cert else {},
            "not_after": cert.get("notAfter"),
            "der_size": len(der) if der else 0,
        }

    try:
        return await loop.run_in_executor(None, _connect)
    except Exception as exc:
        return {"error": str(exc)[:200]}


def _expires_in_days(not_after: str | None) -> int | None:
    if not not_after:
        return None
    from datetime import datetime, timezone
    try:
        dt = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (dt - datetime.now(timezone.utc)).days


@rate_limit_strict(max_per_hour=120)
@log_osint_action(risk_level=RiskLevel.LOW, module="dendani_ssl_audit")
@dendani_only("target")
async def audit_ssl(target: str, port: int = 443, _actor: str = "scheduler",
                    _consent_id: str | None = None) -> dict[str, Any]:
    """Audit SSL d'un domaine Dendani. Refus auto sinon."""
    raw = await _probe_ssl(target, port)
    if "error" in raw:
        rep = SslReport(target=target, grade="F", issuer=None,
                        expires_in_days=None, protocols=[],
                        weak_ciphers=[], issues=[f"connect: {raw['error']}"])
        return _to_dict(rep)

    protocols = [raw.get("version") or ""]
    issues: list[str] = []
    issuer_cn = (raw.get("issuer") or {}).get("commonName")
    if not issuer_cn:
        issues.append("self-signed-or-no-issuer")
    expires_in = _expires_in_days(raw.get("not_after"))
    if expires_in is not None and expires_in < 0:
        issues.append("expired")
    elif expires_in is not None and expires_in < 14:
        issues.append(f"expires-soon-{expires_in}d")

    cipher = (raw.get("cipher") or "").upper()
    weak = []
    for w in ("RC4", "DES", "3DES", "EXPORT", "NULL", "MD5"):
        if w in cipher:
            weak.append(cipher)
            break

    rep = SslReport(target=target, grade="?", issuer=issuer_cn,
                    expires_in_days=expires_in, protocols=protocols,
                    weak_ciphers=weak, issues=issues)
    rep.grade = _grade({"issues": issues, "weak_ciphers": weak, "protocols": protocols})
    return _to_dict(rep)


def _to_dict(rep: SslReport) -> dict[str, Any]:
    return {
        "target": rep.target,
        "grade": rep.grade,
        "issuer": rep.issuer,
        "expires_in_days": rep.expires_in_days,
        "protocols": rep.protocols,
        "weak_ciphers": rep.weak_ciphers,
        "issues": rep.issues,
    }


async def audit_all_dendani() -> list[dict[str, Any]]:
    """Helper : passe tous les domaines whitelistes Dendani."""
    results = []
    for d in DENDANI_DOMAIN_WHITELIST:
        try:
            results.append(await audit_ssl(target=d))
        except Exception as exc:
            results.append({"target": d, "error": str(exc)[:200]})
    return results


__all__ = ["audit_ssl", "audit_all_dendani", "SslReport"]
