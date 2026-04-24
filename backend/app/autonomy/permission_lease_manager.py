"""V5.1 BLOC 2 - Permission Lease Manager.

Donne au systeme des permissions delimitees dans le temps + le budget :
  - scope="payment.datadog"  cap_amount=50 USD  expires_at=+30j usage_cap=3
Au-dela de l'enveloppe, le lease est revoque et une nouvelle demande est
necessaire (evite que "j'autorise Datadog" se transforme en "j'autorise
toutes les depenses SaaS pour toujours").
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg


@dataclass
class Lease:
    id: int
    task_id: str | None
    scope: str
    cap_amount: float | None
    cap_currency: str | None
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    usage_count: int
    usage_cap: int

    @property
    def active(self) -> bool:
        now = datetime.now(UTC)
        return (self.revoked_at is None and self.expires_at > now
                and self.usage_count < self.usage_cap)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "task_id": self.task_id, "scope": self.scope,
            "cap_amount": float(self.cap_amount) if self.cap_amount else None,
            "cap_currency": self.cap_currency,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "usage_count": self.usage_count, "usage_cap": self.usage_cap,
            "active": self.active,
        }


async def grant(
    pool: asyncpg.Pool, scope: str, *,
    duration_days: int = 30, cap_amount: float | None = None,
    cap_currency: str | None = None, usage_cap: int = 1,
    task_id: str | None = None, granter: str = "ahmed",
) -> Lease:
    expires = datetime.now(UTC) + timedelta(days=duration_days)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO permission_leases(
                task_id, scope, cap_amount, cap_currency,
                expires_at, usage_cap, granter
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            UUID(task_id) if task_id else None,
            scope[:120], cap_amount, cap_currency[:10] if cap_currency else None,
            expires, usage_cap, granter[:120],
        )
    return _to_lease(row)


async def find_active(
    pool: asyncpg.Pool, scope: str,
) -> Lease | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT * FROM permission_leases
            WHERE scope = $1 AND revoked_at IS NULL AND expires_at > NOW()
              AND usage_count < usage_cap
            ORDER BY expires_at DESC LIMIT 1
            """,
            scope[:120],
        )
    return _to_lease(row) if row else None


async def consume(
    pool: asyncpg.Pool, lease_id: int,
    amount: float | None = None,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM permission_leases WHERE id = $1", lease_id,
        )
        if row is None:
            return {"ok": False, "reason": "lease inconnu"}
        lease = _to_lease(row)
        if not lease.active:
            return {"ok": False, "reason": "lease inactif/expire"}
        if amount is not None and lease.cap_amount is not None:
            if amount > float(lease.cap_amount):
                return {"ok": False,
                        "reason": (f"amount {amount} > cap "
                                    f"{lease.cap_amount} {lease.cap_currency}")}
        await conn.execute(
            "UPDATE permission_leases SET usage_count = usage_count + 1 "
            "WHERE id = $1", lease_id,
        )
    return {"ok": True, "lease_id": lease_id,
            "scope": lease.scope, "remaining": lease.usage_cap - (lease.usage_count + 1)}


async def revoke(pool: asyncpg.Pool, lease_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE permission_leases SET revoked_at = NOW() "
            "WHERE id = $1 AND revoked_at IS NULL RETURNING id",
            lease_id,
        )
    return row is not None


async def list_active(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM permission_leases
            WHERE revoked_at IS NULL AND expires_at > NOW()
            ORDER BY expires_at ASC
            """,
        )
    return [_to_lease(r).to_dict() for r in rows]


def _to_lease(row: asyncpg.Record) -> Lease:
    return Lease(
        id=int(row["id"]),
        task_id=str(row["task_id"]) if row["task_id"] else None,
        scope=row["scope"],
        cap_amount=float(row["cap_amount"]) if row["cap_amount"] else None,
        cap_currency=row["cap_currency"],
        granted_at=row["granted_at"],
        expires_at=row["expires_at"],
        revoked_at=row["revoked_at"],
        usage_count=int(row["usage_count"]),
        usage_cap=int(row["usage_cap"]),
    )
