"""Upgrade 6 - Tool Integrator : une fois un outil provisionne, generer le connecteur.

Flow :
 1. Lire l'URL de l'outil dans tool_registry
 2. Tenter de decouvrir les endpoints : /openapi.json, /swagger.json, /api/v1/*
 3. Enregistrer les capacites detectees dans tool_registry.capabilities
 4. Tester la connexion (probe) et mettre a jour le status
 5. Rendre l'outil utilisable par les agents via un connecteur leger
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx

from app.integrations.vault_client import get_vault
from app.orchestration import audit_events, tool_registry

logger = logging.getLogger(__name__)


OPENAPI_PATHS = ("/openapi.json", "/swagger.json", "/api-docs", "/v3/api-docs")


@dataclass
class IntegrationOutcome:
    tool_id: str
    ok: bool
    capabilities: list[str]
    openapi_url: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id, "ok": self.ok,
            "capabilities": self.capabilities,
            "openapi_url": self.openapi_url,
            "message": self.message,
        }


async def _auth_headers(tool: dict[str, Any]) -> dict[str, str]:
    if not tool.get("api_key_vault_path"):
        return {}
    vault = get_vault()
    data = vault.get(tool["api_key_vault_path"], default={})
    key = data.get("api_key") if isinstance(data, dict) else None
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


async def _discover_openapi(
    base_url: str, headers: dict[str, str],
) -> tuple[str | None, list[str]]:
    """Tente /openapi.json etc. Retourne (url_detectee, liste_capacites)."""
    async with httpx.AsyncClient(timeout=5.0, headers=headers) as c:
        for path in OPENAPI_PATHS:
            url = base_url.rstrip("/") + path
            try:
                r = await c.get(url)
                if r.status_code == 200:
                    data = r.json()
                    caps = _capabilities_from_openapi(data)
                    return url, caps
            except Exception:
                continue
    return None, []


def _capabilities_from_openapi(doc: dict[str, Any]) -> list[str]:
    """Extrait les operations (tag ou method:path) comme capacites."""
    caps: set[str] = set()
    paths = doc.get("paths", {})
    if isinstance(paths, dict):
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method in ("get", "post", "put", "delete", "patch"):
                    if isinstance(op, dict) and op.get("tags"):
                        caps.update(f"{t}.{method}" for t in op["tags"])
                    else:
                        caps.add(f"{method}:{path}")
    # Reduction : garder <= 40 capacites pour rester lisible
    return sorted(caps)[:40]


async def integrate(pool: asyncpg.Pool, tool_id: str) -> IntegrationOutcome:
    tool = await tool_registry.get(pool, tool_id)
    if not tool:
        return IntegrationOutcome(
            tool_id=tool_id, ok=False, capabilities=[],
            openapi_url=None, message="tool not in registry",
        )
    base_url = tool.get("url") or ""
    if not base_url:
        return IntegrationOutcome(
            tool_id=tool_id, ok=False, capabilities=[],
            openapi_url=None, message="no url",
        )
    headers = await _auth_headers(tool)
    openapi_url, caps = await _discover_openapi(base_url, headers)
    if caps:
        await tool_registry.update_capabilities(pool, tool_id, caps)
        await tool_registry.set_status(pool, tool_id, "connected")
        await audit_events.emit(
            pool, action="tool_integrated", actor="tool_integrator",
            payload={"tool_id": tool_id, "openapi_url": openapi_url,
                     "capabilities_count": len(caps)},
        )
        return IntegrationOutcome(
            tool_id=tool_id, ok=True, capabilities=caps,
            openapi_url=openapi_url,
            message=f"{len(caps)} capacites detectees",
        )
    # Pas d'OpenAPI detecte - au moins un healthcheck
    async with httpx.AsyncClient(timeout=5.0, headers=headers) as c:
        try:
            r = await c.get(base_url)
            reachable = r.status_code < 500
        except Exception:
            reachable = False
    status = "connected" if reachable else "disconnected"
    await tool_registry.set_status(pool, tool_id, status)
    return IntegrationOutcome(
        tool_id=tool_id, ok=reachable, capabilities=[],
        openapi_url=None,
        message="OpenAPI non detecte ; base URL joignable" if reachable else "base URL indisponible",
    )
