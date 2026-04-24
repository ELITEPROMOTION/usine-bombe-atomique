"""API domaines : list + detail + validate + process."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.core import DomainContext, DomainRegistry, DomainRouter

router = APIRouter(prefix="/domains", tags=["domains"])


def _ctx_from_body(body: dict[str, Any], domain_id: str) -> DomainContext:
    return DomainContext(
        tenant_id=body.get("tenant_id", "default"),
        user_id=body.get("user_id"),
        domain_id=domain_id,
        permissions=frozenset(body.get("permissions", [f"{domain_id}:*"])),
    )


@router.get("/list")
async def domains_list() -> dict[str, Any]:
    registry = DomainRegistry.instance()
    domains = registry.list_domains()
    return {"count": len(domains), "domains": domains}


@router.get("/{domain_id}")
async def domain_detail(domain_id: str) -> dict[str, Any]:
    try:
        domain = DomainRegistry.instance().get(domain_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    from app.domains import RULES_ENGINE
    rules = RULES_ENGINE.get_rules(domain_id)
    return {
        "domain_id": domain.domain_id,
        "version": domain.version,
        "description": domain.description,
        "operations": list(domain.supported_operations),
        "schema": domain.schema,
        "rules_count": len(rules),
        "rules": [
            {"id": r.id, "description": r.description, "priority": r.priority,
             "enabled": r.enabled}
            for r in rules[:50]
        ],
    }


@router.post("/{domain_id}/validate")
async def domain_validate(
    domain_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    try:
        ctx = _ctx_from_body(body, domain_id)
        router_ = DomainRouter()
        result = await router_.validate(body.get("input", {}), ctx)
        return result.model_dump()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/{domain_id}/process")
async def domain_process(
    domain_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    try:
        ctx = _ctx_from_body(body, domain_id)
        router_ = DomainRouter()
        result = await router_.process(
            body.get("input", {}), ctx,
            operation=body.get("operation", "process"),
        )
        return result.model_dump()
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
