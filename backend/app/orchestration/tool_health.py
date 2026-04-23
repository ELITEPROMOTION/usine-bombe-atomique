"""Upgrade 20 - Healthchecker outils.

Verifie periodiquement que chaque outil connecte repond. En cas d'echec,
declenche une alerte (audit_events.emit) et tente une reconnexion legere.

Par defaut, probing HTTP sur `url` (GET + timeout 5s) ; pour les outils
non-HTTP, on laisse au connecteur le soin d'implementer `probe()`.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncpg
import httpx

from app.orchestration import audit_events, tool_registry

logger = logging.getLogger(__name__)


async def probe_tool(tool: dict[str, Any]) -> str:
    """Retourne 'ok' | 'degraded' | 'down' | 'skipped'."""
    url = tool.get("url") or ""
    if not url:
        return "skipped"
    if tool.get("tool_type") not in ("saas", "self_hosted", "api"):
        return "skipped"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url)
            if r.status_code < 500:
                return "ok" if r.status_code < 400 else "degraded"
            return "down"
    except Exception as exc:
        logger.debug("probe %s failed: %s", tool.get("tool_id"), exc)
        return "down"


async def check_all(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    tools = await tool_registry.list_all(pool, status="connected")
    results: list[dict[str, Any]] = []
    coros = [probe_tool(t) for t in tools]
    statuses = await asyncio.gather(*coros, return_exceptions=False)
    for t, s in zip(tools, statuses, strict=False):
        await tool_registry.record_health(pool, t["tool_id"], s)
        results.append({"tool_id": t["tool_id"], "status": s})
        if s == "down":
            await audit_events.emit(
                pool, action="tool_down", actor="tool_health",
                payload={"tool_id": t["tool_id"], "url": t.get("url")},
            )
            await tool_registry.set_status(pool, t["tool_id"], "disconnected")
    return results


async def reconnect(pool: asyncpg.Pool, tool_id: str) -> str:
    """Tente une probe rapide et remet le statut a 'connected' si OK."""
    tool = await tool_registry.get(pool, tool_id)
    if not tool:
        return "not_found"
    s = await probe_tool(tool)
    if s == "ok":
        await tool_registry.set_status(pool, tool_id, "connected")
        await tool_registry.record_health(pool, tool_id, "ok")
        await audit_events.emit(
            pool, action="tool_reconnected", actor="tool_health",
            payload={"tool_id": tool_id},
        )
    return s
