"""Upgrade 19 - Registre des outils connectes (tool_registry).

Table migree en 010. Permet aux agents de savoir quels outils externes
sont branches, ou chercher leur cle API (Vault path) et leurs capacites.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class Tool:
    tool_id: str
    name: str
    tool_type: str   # saas | self_hosted | mcp | api | cli
    url: str = ""
    api_key_vault_path: str = ""
    status: str = "pending_setup"
    capabilities: list[str] = field(default_factory=list)


async def register(pool: asyncpg.Pool, tool: Tool) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tool_registry
              (tool_id, name, tool_type, url, api_key_vault_path, status, capabilities)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)
            ON CONFLICT (tool_id) DO UPDATE SET
              name = EXCLUDED.name, tool_type = EXCLUDED.tool_type,
              url = EXCLUDED.url, api_key_vault_path = EXCLUDED.api_key_vault_path,
              status = EXCLUDED.status, capabilities = EXCLUDED.capabilities
            RETURNING id
            """,
            tool.tool_id, tool.name, tool.tool_type, tool.url,
            tool.api_key_vault_path, tool.status, json.dumps(tool.capabilities),
        )
    return str(row["id"])


async def set_status(pool: asyncpg.Pool, tool_id: str, status: str) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE tool_registry SET status=$2,
              connected_at = CASE WHEN $2='connected' THEN NOW() ELSE connected_at END
            WHERE tool_id=$1 RETURNING id
            """, tool_id, status,
        )
    return row is not None


async def update_capabilities(pool: asyncpg.Pool, tool_id: str,
                                capabilities: list[str]) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE tool_registry SET capabilities=$2::jsonb "
            "WHERE tool_id=$1 RETURNING id",
            tool_id, json.dumps(sorted(set(capabilities))),
        )
    return row is not None


async def record_health(
    pool: asyncpg.Pool, tool_id: str, status: str,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE tool_registry
            SET last_health_at = NOW(), last_health_status = $2
            WHERE tool_id = $1
            """, tool_id, status[:20],
        )


async def get(pool: asyncpg.Pool, tool_id: str) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tool_id, name, tool_type, url, api_key_vault_path, status, "
            "capabilities, last_health_at, last_health_status, connected_at, created_at "
            "FROM tool_registry WHERE tool_id = $1", tool_id,
        )
    if not row:
        return None
    return _row_to_dict(row)


async def list_all(pool: asyncpg.Pool,
                    status: str | None = None) -> list[dict[str, Any]]:
    sql = ("SELECT tool_id, name, tool_type, url, api_key_vault_path, status, "
           "capabilities, last_health_at, last_health_status, connected_at, created_at "
           "FROM tool_registry")
    args: list[Any] = []
    if status:
        sql += " WHERE status = $1"
        args.append(status)
    sql += " ORDER BY tool_id"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    caps = row["capabilities"]
    if isinstance(caps, str):
        caps = json.loads(caps)
    return {
        "tool_id": row["tool_id"], "name": row["name"],
        "tool_type": row["tool_type"], "url": row["url"],
        "api_key_vault_path": row["api_key_vault_path"],
        "status": row["status"], "capabilities": caps or [],
        "last_health_at": row["last_health_at"].isoformat() if row["last_health_at"] else None,
        "last_health_status": row["last_health_status"],
        "connected_at": row["connected_at"].isoformat() if row["connected_at"] else None,
        "created_at": row["created_at"].isoformat(),
    }
