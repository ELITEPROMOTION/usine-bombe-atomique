"""V5.1 BLOC 2 - Hard Boundary Registry.

Registre des scopes qui DOIVENT escalader vers Ahmed, quelle que soit la
confiance du systeme. Interroge par human_necessity_proof et par le
autonomy_ladder : un scope 'hard' force le passage ESCALATE.

Seed initial dans la migration 013 :
  - payment.any
  - credentials.new_account
  - prod.rollback_last_resort
  - gdpr.waiver
  - dendani.reputation_risk
"""
from __future__ import annotations

from typing import Any

import asyncpg


async def is_hard(
    pool: asyncpg.Pool, scope: str,
) -> dict[str, Any] | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT scope, description, requires_type "
            "FROM hard_boundary_registry WHERE scope = $1",
            scope[:120],
        )
    return dict(row) if row else None


async def check(
    pool: asyncpg.Pool, scopes: list[str],
) -> list[dict[str, Any]]:
    """Retourne tous les hard boundaries matchant des scopes donnes."""
    hits: list[dict[str, Any]] = []
    for s in scopes:
        h = await is_hard(pool, s)
        if h:
            hits.append(h)
    return hits


async def register(
    pool: asyncpg.Pool, scope: str, description: str, requires_type: str,
) -> bool:
    if requires_type not in ("A", "B", "C"):
        raise ValueError("requires_type must be A, B or C")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO hard_boundary_registry(scope, description, requires_type)
            VALUES ($1, $2, $3)
            ON CONFLICT (scope) DO UPDATE SET
              description = EXCLUDED.description,
              requires_type = EXCLUDED.requires_type
            """,
            scope[:120], description, requires_type,
        )
    return True


async def list_all(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT scope, description, requires_type, created_at "
            "FROM hard_boundary_registry ORDER BY scope",
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        d["created_at"] = d["created_at"].isoformat()
        out.append(d)
    return out
