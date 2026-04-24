"""Feature flags production-grade.

Evaluation hierarchique (plus specifique d'abord) :
    1. enabled_users (UUID[]) -> override explicite user
    2. enabled_tenants (UUID[]) -> override explicite tenant
    3. rollout_percent (0-100) -> hash(user_id+flag_name) % 100 < percent
    4. enabled_globally (bool)

Cache Redis 30s pour minimiser les round-trips Postgres.
Tracking dans feature_flag_events (agregation par flag).
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import asyncpg

logger = logging.getLogger("uba.core.feature_flags")

_CACHE_KEY_PREFIX = "uba:ff:"
_CACHE_TTL_S = 30


@dataclass
class FlagDefinition:
    flag_name: str
    description: str | None
    enabled_globally: bool
    enabled_tenants: list[str]
    enabled_users: list[str]
    rollout_percent: int
    condition_cel: str | None
    auto_disable_on_error: bool
    error_threshold_percent: int


def _hash_bucket(user_id: str | None, flag_name: str) -> int:
    """Bucket deterministe 0-99 pour rollout%."""
    seed = f"{user_id or 'anon'}::{flag_name}"
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % 100


class FeatureFlagsService:
    """Evaluateur feature flags avec cache Redis."""

    def __init__(self, pool: asyncpg.Pool, redis_client: Any | None = None) -> None:
        self.pool = pool
        self.redis = redis_client

    async def _load_flag(self, flag_name: str) -> FlagDefinition | None:
        # 1. Cache hit
        if self.redis is not None:
            try:
                cached = await self.redis.get(_CACHE_KEY_PREFIX + flag_name)
                if cached:
                    data = json.loads(cached)
                    return FlagDefinition(**data)
            except Exception as exc:
                logger.debug("ff cache read failed: %s", exc)
        # 2. DB
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT flag_name, description, enabled_globally,
                       enabled_tenants, enabled_users, rollout_percent,
                       condition_cel, auto_disable_on_error,
                       error_threshold_percent
                FROM feature_flags WHERE flag_name = $1
                """, flag_name,
            )
        if row is None:
            return None
        flag = FlagDefinition(
            flag_name=row["flag_name"],
            description=row["description"],
            enabled_globally=row["enabled_globally"],
            enabled_tenants=[str(x) for x in row["enabled_tenants"]],
            enabled_users=[str(x) for x in row["enabled_users"]],
            rollout_percent=int(row["rollout_percent"]),
            condition_cel=row["condition_cel"],
            auto_disable_on_error=row["auto_disable_on_error"],
            error_threshold_percent=int(row["error_threshold_percent"]),
        )
        # Cache
        if self.redis is not None:
            try:
                await self.redis.setex(
                    _CACHE_KEY_PREFIX + flag_name, _CACHE_TTL_S,
                    json.dumps(flag.__dict__, default=str),
                )
            except Exception as exc:
                logger.debug("ff cache write failed: %s", exc)
        return flag

    async def is_enabled(
        self, flag_name: str,
        user_id: str | None = None,
        tenant_id: str | None = None,
        default: bool = False,
    ) -> bool:
        """Evalue un feature flag.

        Hierarchie (premiere match gagne) :
          1. user_id dans enabled_users -> True
          2. tenant_id dans enabled_tenants -> True
          3. rollout_percent > 0 et hash(user_id+flag) < percent -> True
          4. enabled_globally
        """
        start = time.perf_counter()
        result = default
        try:
            flag = await self._load_flag(flag_name)
            if flag is None:
                return default
            # 1. Explicit user override
            if user_id and str(user_id) in flag.enabled_users:
                result = True
            # 2. Explicit tenant override
            elif tenant_id and str(tenant_id) in flag.enabled_tenants:
                result = True
            # 3. Percent rollout
            elif flag.rollout_percent > 0 and \
                 _hash_bucket(user_id, flag_name) < flag.rollout_percent:
                result = True
            # 4. Global
            else:
                result = flag.enabled_globally
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO feature_flag_events
                            (flag_name, event_type, tenant_id, user_id,
                             result, duration_ms)
                        VALUES ($1, 'evaluated', $2::uuid, $3::uuid, $4, $5)
                        """,
                        flag_name, tenant_id, user_id, result, duration_ms,
                    )
            except Exception as exc:
                logger.debug("ff event log failed: %s", exc)
        return result

    async def invalidate_cache(self, flag_name: str) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.delete(_CACHE_KEY_PREFIX + flag_name)
        except Exception as exc:
            logger.debug("ff invalidate failed: %s", exc)

    async def list_flags(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT flag_name, description, enabled_globally,
                       rollout_percent, array_length(enabled_tenants, 1) AS tenants_n,
                       array_length(enabled_users, 1) AS users_n,
                       created_at, updated_at, updated_by
                FROM feature_flags
                ORDER BY flag_name
                """,
            )
        return [
            {
                "flag_name": r["flag_name"],
                "description": r["description"],
                "enabled_globally": bool(r["enabled_globally"]),
                "rollout_percent": int(r["rollout_percent"]),
                "enabled_tenants_count": int(r["tenants_n"] or 0),
                "enabled_users_count": int(r["users_n"] or 0),
                "updated_at": r["updated_at"].isoformat(),
                "updated_by": r["updated_by"],
            }
            for r in rows
        ]

    async def toggle(
        self, flag_name: str, enabled: bool, updated_by: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feature_flags
                SET enabled_globally = $2, updated_at = NOW(),
                    updated_by = $3
                WHERE flag_name = $1
                """, flag_name, enabled, updated_by,
            )
        await self.invalidate_cache(flag_name)

    async def set_rollout(
        self, flag_name: str, percent: int, updated_by: str,
    ) -> None:
        percent = max(0, min(100, percent))
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE feature_flags
                SET rollout_percent = $2, updated_at = NOW(),
                    updated_by = $3
                WHERE flag_name = $1
                """, flag_name, percent, updated_by,
            )
        await self.invalidate_cache(flag_name)

    async def metrics(
        self, flag_name: str, hours: int = 24,
    ) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) AS evaluations,
                    SUM(CASE WHEN result THEN 1 ELSE 0 END) AS enabled_count,
                    SUM(CASE WHEN event_type='error' THEN 1 ELSE 0 END) AS errors,
                    AVG(duration_ms) AS avg_ms
                FROM feature_flag_events
                WHERE flag_name = $1
                  AND created_at > NOW() - ($2 || ' hours')::interval
                """, flag_name, str(hours),
            )
        total = int(row["evaluations"] or 0)
        enabled = int(row["enabled_count"] or 0)
        errors = int(row["errors"] or 0)
        return {
            "flag_name": flag_name,
            "hours": hours,
            "evaluations": total,
            "enabled_rate": (enabled / total) if total else 0.0,
            "error_rate": (errors / total) if total else 0.0,
            "avg_duration_ms": float(row["avg_ms"] or 0),
        }
