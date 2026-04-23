"""Endpoints V4.3 : outils, provisioning, pending user inputs."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.database import get_pool
from app.integrations.sonarqube_client import SonarQubeClient
from app.integrations.vault_client import get_vault, seed_from_env
from app.orchestration import compliance_matrix, sensitive_collector, tool_health, tool_registry
from app.provisioning import tool_integrator, tool_provisioner
from app.provisioning.browser_ops_agent import list_flows

router = APIRouter()


# --- Tools -----------------------------------------------------------

@router.get("/tools")
async def list_tools(status: str | None = None) -> list[dict]:
    pool = get_pool()
    return await tool_registry.list_all(pool, status=status)


@router.get("/tools/{tool_id}")
async def get_tool(tool_id: str) -> dict:
    pool = get_pool()
    t = await tool_registry.get(pool, tool_id)
    if not t:
        raise HTTPException(404, "tool not found")
    return t


@router.post("/tools/{tool_id}/integrate")
async def integrate_tool(tool_id: str) -> dict:
    pool = get_pool()
    out = await tool_integrator.integrate(pool, tool_id)
    return out.to_dict()


@router.get("/tools/health/check")
async def tools_health() -> list[dict]:
    pool = get_pool()
    return await tool_health.check_all(pool)


@router.post("/tools/{tool_id}/reconnect")
async def tool_reconnect(tool_id: str) -> dict:
    pool = get_pool()
    s = await tool_health.reconnect(pool, tool_id)
    return {"tool_id": tool_id, "probe_result": s}


@router.get("/flows")
async def list_provision_flows() -> list[str]:
    return list_flows()


# --- Provisioning ---------------------------------------------------

@router.post("/tools/{tool_id}/provision")
async def provision(tool_id: str, payload: dict | None = None) -> dict:
    pool = get_pool()
    body = payload or {}
    task_id = body.get("task_id") or body.get("taskId")
    if not task_id:
        raise HTTPException(400, "task_id required")
    provided = body.get("values") or {}
    dry_run = bool(body.get("dry_run", True))
    outcome = await tool_provisioner.provision(
        pool, task_id=task_id, tool_id=tool_id,
        provided_values=provided, dry_run=dry_run,
    )
    return {
        "tool_id": outcome.tool_id, "status": outcome.status,
        "pending_request_id": outcome.pending_request_id,
        "vault_path": outcome.vault_path, "message": outcome.message,
    }


# --- Pending user inputs --------------------------------------------

@router.get("/pending-user-inputs")
async def pending_inputs(task_id: str | None = None, limit: int = 50) -> list[dict]:
    pool = get_pool()
    return await sensitive_collector.list_awaiting(pool, task_id=task_id, limit=limit)


@router.post("/pending-user-inputs/{request_id}/submit")
async def submit_input(request_id: str, payload: dict) -> dict:
    pool = get_pool()
    ok = await sensitive_collector.submit_response(pool, request_id, payload or {})
    if not ok:
        raise HTTPException(404, "request not awaiting or already submitted")
    return {"ok": True, "request_id": request_id}


# --- Compliance matrix ---------------------------------------------

@router.get("/compliance/{task_id}")
async def compliance_by_task(task_id: UUID) -> list[dict]:
    pool = get_pool()
    return await compliance_matrix.list_by_task(pool, str(task_id))


@router.get("/compliance/{task_id}/summary")
async def compliance_summary(task_id: UUID) -> dict:
    pool = get_pool()
    return await compliance_matrix.summary(pool, str(task_id))


# --- Integrations status --------------------------------------------

@router.get("/integrations/status")
async def integrations_status() -> dict[str, Any]:
    vault = get_vault()
    sonar = SonarQubeClient()
    return {
        "vault": {"available": vault.is_available()},
        "sonarqube": await sonar.health(),
    }


@router.post("/integrations/vault/seed")
async def vault_seed() -> dict[str, Any]:
    vault = get_vault()
    if not vault.is_available():
        raise HTTPException(503, "vault unavailable")
    return {"seeded": seed_from_env(vault)}
