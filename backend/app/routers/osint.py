"""V8 router : OSINT endpoints.

Surface uniquement les operations defensives (lecture audit, status, lancement
modules dendani-only). Les pentest consentis passent par /api/v1/osint/pentest/*
qui requierent un consent_id valide (admin only).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_pool
from app.osint.legal_framework import (
    AuditTrail,
    Consent,
    ConsentManager,
    ScopeEnforcer,
)

logger = logging.getLogger("uba.routers.osint")
router = APIRouter()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@router.get("/audit/export")
async def export_audit(since: str | None = None,
                       until: str | None = None,
                       limit: int = Query(default=500, le=5000)) -> dict[str, Any]:
    from datetime import datetime
    pool = get_pool()
    trail = AuditTrail(pool)
    s = datetime.fromisoformat(since) if since else None
    u = datetime.fromisoformat(until) if until else None
    events = await trail.export(since=s, until=u)
    return {"events": events[:limit], "count": len(events)}


@router.get("/audit/integrity")
async def audit_integrity_check() -> dict[str, Any]:
    pool = get_pool()
    trail = AuditTrail(pool)
    rep = await trail.verify_chain()
    return rep


# ---------------------------------------------------------------------------
# Consents (admin)
# ---------------------------------------------------------------------------


class ConsentIn(BaseModel):
    target: str = Field(..., min_length=3, max_length=255)
    actions: list[str] = Field(..., min_length=1, max_length=20)
    contractor: str = Field(..., min_length=2, max_length=255)
    contract_pdf_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    expires_at_iso: str


@router.post("/consents")
async def add_consent(payload: ConsentIn) -> dict[str, Any]:
    from datetime import datetime
    pool = get_pool()
    mgr = ConsentManager(pool)
    expires = datetime.fromisoformat(payload.expires_at_iso)
    cid = await mgr.add_consent(
        target=payload.target, actions=payload.actions,
        contractor=payload.contractor,
        contract_pdf_sha256=payload.contract_pdf_sha256,
        expires_at=expires,
    )
    return {"consent_id": cid}


@router.delete("/consents/{consent_id}")
async def revoke_consent(consent_id: UUID, reason: str = "manual") -> dict[str, Any]:
    pool = get_pool()
    mgr = ConsentManager(pool)
    await mgr.revoke_consent(str(consent_id), reason)
    return {"revoked": True}


@router.get("/consents")
async def list_consents() -> dict[str, Any]:
    pool = get_pool()
    mgr = ConsentManager(pool)
    consents = await mgr.list_active_consents()
    return {
        "count": len(consents),
        "consents": [{
            "consent_id": c.consent_id, "target": c.target,
            "actions": c.actions, "contractor": c.contractor,
            "signed_at": c.signed_at.isoformat() if c.signed_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        } for c in consents],
    }


# ---------------------------------------------------------------------------
# Module status / triggers
# ---------------------------------------------------------------------------


@router.get("/modules")
async def list_modules() -> dict[str, Any]:
    return {
        "modules": [
            {"name": "dendani_ssl_audit", "category": "security_defensive",
             "scope": "dendani_only", "risk": "low"},
            {"name": "dendani_breach_check", "category": "security_defensive",
             "scope": "dendani_only", "risk": "low"},
            {"name": "dendani_dependency_scanner", "category": "security_defensive",
             "scope": "dendani_only", "risk": "medium"},
            {"name": "dendani_dns_audit", "category": "security_defensive",
             "scope": "dendani_only", "risk": "low"},
            {"name": "dendani_brand_monitor", "category": "public_watch",
             "scope": "public_sources", "risk": "low"},
            {"name": "competitor_public_watch", "category": "public_watch",
             "scope": "public_sources", "risk": "low"},
            {"name": "market_intelligence_dz", "category": "public_watch",
             "scope": "public_sources", "risk": "low"},
            {"name": "regulatory_watch_dz", "category": "public_watch",
             "scope": "public_sources", "risk": "low"},
            {"name": "consented_pentest_engine", "category": "consented_pentest",
             "scope": "requires_consent", "risk": "high"},
            {"name": "vulnerability_assessment_consented", "category": "consented_pentest",
             "scope": "requires_consent", "risk": "high"},
            {"name": "threat_intel_aggregator", "category": "threat_intel",
             "scope": "public_sources", "risk": "low"},
            {"name": "dark_web_monitor_lite", "category": "threat_intel",
             "scope": "dendani_only", "risk": "medium"},
        ],
    }


@router.get("/dashboard/summary")
async def dashboard_summary() -> dict[str, Any]:
    """Synthese pour la page /osint."""
    pool = get_pool()
    async with pool.acquire() as conn:
        counts_by_decision = await conn.fetch(
            "SELECT decision, COUNT(*) AS c FROM osint_audit_trail "
            "WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY decision",
        )
        counts_by_module = await conn.fetch(
            "SELECT module, COUNT(*) AS c FROM osint_audit_trail "
            "WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY module ORDER BY c DESC LIMIT 12",
        )
        recent_denials = await conn.fetch(
            "SELECT module, target, payload_json, created_at FROM osint_audit_trail "
            "WHERE decision = 'denied' ORDER BY created_at DESC LIMIT 10",
        )
        active_consents = await conn.fetchval(
            "SELECT COUNT(*) FROM osint_consents "
            "WHERE revoked_at IS NULL AND expires_at > NOW()",
        )
    return {
        "decisions_7d": [{"decision": r["decision"], "count": r["c"]} for r in counts_by_decision],
        "by_module_7d": [{"module": r["module"], "count": r["c"]} for r in counts_by_module],
        "recent_denials": [{
            "module": r["module"], "target": r["target"],
            "created_at": r["created_at"].isoformat(),
        } for r in recent_denials],
        "active_consents": int(active_consents or 0),
    }
