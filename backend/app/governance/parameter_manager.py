"""V5.2 BLOC 2 - Parameter Manager.

API pour manipuler system_parameters avec :
  - validation des bornes (LEARNABLE : allowed_min..allowed_max)
  - versioning auto
  - rollback rapide via rollback_value
  - audit via evidence_ledger + audit_events
  - restrictions d'actor : super-admin (Ahmed) seul pour PARAMETRIZABLE,
    nightly_optimizer autorise pour LEARNABLE dans les bornes.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.governance._json_utils import parse_jsonb
from app.orchestration import audit_events, evidence_ledger

logger = logging.getLogger(__name__)


class ParameterError(Exception):
    """Erreur de validation parametre."""


# Actors autorises par categorie
ALLOWED_ACTORS = {
    "PARAMETRIZABLE": {"ahmed", "super_admin"},
    "LEARNABLE":       {"ahmed", "super_admin", "nightly_optimizer",
                         "canary_engine", "auto_tuner"},
}


@dataclass
class Parameter:
    key: str
    value: Any
    category: str
    allowed_min: float | None
    allowed_max: float | None
    requires_approval: bool
    version: int
    changed_by: str
    justification: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "value": self.value, "category": self.category,
            "allowed_min": float(self.allowed_min) if self.allowed_min is not None else None,
            "allowed_max": float(self.allowed_max) if self.allowed_max is not None else None,
            "requires_approval": self.requires_approval,
            "version": self.version, "changed_by": self.changed_by,
            "justification": self.justification,
        }


async def get(pool: asyncpg.Pool, key: str) -> Parameter | None:
    """Derniere version active pour la cle."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT parameter_key, parameter_value, parameter_category,
                   allowed_min, allowed_max, requires_approval,
                   version, changed_by, justification
            FROM system_parameters
            WHERE parameter_key = $1
            ORDER BY version DESC LIMIT 1
            """, key,
        )
    if not row:
        return None
    value = parse_jsonb(row["parameter_value"])
    return Parameter(
        key=row["parameter_key"], value=value,
        category=row["parameter_category"],
        allowed_min=row["allowed_min"], allowed_max=row["allowed_max"],
        requires_approval=row["requires_approval"],
        version=row["version"], changed_by=row["changed_by"],
        justification=row["justification"],
    )


async def get_value(pool: asyncpg.Pool, key: str, default: Any = None) -> Any:
    p = await get(pool, key)
    return p.value if p is not None else default


async def set_value(
    pool: asyncpg.Pool, key: str, value: Any, *,
    actor: str, justification: str,
) -> Parameter:
    current = await get(pool, key)
    if current is None:
        raise ParameterError(f"parametre inconnu : {key}")
    # Actor check
    allowed = ALLOWED_ACTORS.get(current.category, set())
    if actor not in allowed:
        raise ParameterError(
            f"actor '{actor}' non autorise pour {current.category} "
            f"(autorises: {sorted(allowed)})")
    # Bounds check (LEARNABLE only)
    if current.category == "LEARNABLE":
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise ParameterError(
                f"{key} est LEARNABLE : valeur numerique attendue") from None
        if current.allowed_min is not None and numeric < float(current.allowed_min):
            raise ParameterError(
                f"{key} = {numeric} < allowed_min ({current.allowed_min})")
        if current.allowed_max is not None and numeric > float(current.allowed_max):
            raise ParameterError(
                f"{key} = {numeric} > allowed_max ({current.allowed_max})")
    # Insert new version
    new_version = current.version + 1
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO system_parameters
              (parameter_key, parameter_value, parameter_category,
               allowed_min, allowed_max, requires_approval,
               version, changed_by, justification, rollback_value)
            VALUES ($1, $2::jsonb, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
            """,
            key, json.dumps(value), current.category,
            current.allowed_min, current.allowed_max, current.requires_approval,
            new_version, actor, justification,
            json.dumps(current.value),
        )
    # Evidence + audit
    payload = {
        "key": key, "old": current.value, "new": value,
        "actor": actor, "version": new_version,
        "justification": justification[:200],
    }
    await evidence_ledger.record(
        pool, kind="override", actor=f"parameter_manager:{actor}",
        payload=payload,
    )
    await audit_events.emit(
        pool, action="parameter_changed", actor=actor, payload=payload,
    )
    logger.info("param %s : %s -> %s (v%d by %s)",
                key, current.value, value, new_version, actor)
    return Parameter(
        key=key, value=value, category=current.category,
        allowed_min=current.allowed_min, allowed_max=current.allowed_max,
        requires_approval=current.requires_approval,
        version=new_version, changed_by=actor, justification=justification,
    )


async def rollback(
    pool: asyncpg.Pool, key: str, versions_back: int = 1, *,
    actor: str = "rollback",
) -> Parameter:
    """Restaure une version anterieure en creant une nouvelle version qui
    copie les valeurs voulues."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT parameter_value, parameter_category,
                   allowed_min, allowed_max, requires_approval
            FROM system_parameters
            WHERE parameter_key = $1 ORDER BY version DESC
            LIMIT $2
            """, key, versions_back + 1,
        )
    if len(rows) <= versions_back:
        raise ParameterError(
            f"impossible de rollback {versions_back} version(s) : trop court")
    target = rows[versions_back]
    value = parse_jsonb(target["parameter_value"])
    return await set_value(
        pool, key, value,
        actor=actor,
        justification=f"rollback -{versions_back} version(s)",
    )


async def history(
    pool: asyncpg.Pool, key: str, limit: int = 20,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT version, parameter_value, changed_by, changed_at,
                   justification
            FROM system_parameters WHERE parameter_key = $1
            ORDER BY version DESC LIMIT $2
            """, key, limit,
        )
    out: list[dict[str, Any]] = []
    for r in rows:
        v = parse_jsonb(r["parameter_value"])
        out.append({
            "version": r["version"], "value": v,
            "changed_by": r["changed_by"],
            "changed_at": r["changed_at"].isoformat(),
            "justification": r["justification"],
        })
    return out


async def list_all(pool: asyncpg.Pool) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM system_parameters_current ORDER BY parameter_key"
        )
    out = []
    for r in rows:
        v = parse_jsonb(r["parameter_value"])
        out.append({
            "key": r["parameter_key"], "value": v,
            "category": r["parameter_category"],
            "min": float(r["allowed_min"]) if r["allowed_min"] else None,
            "max": float(r["allowed_max"]) if r["allowed_max"] else None,
            "requires_approval": r["requires_approval"],
            "version": r["version"], "changed_by": r["changed_by"],
            "changed_at": r["changed_at"].isoformat(),
        })
    return out


async def get_bounds(
    pool: asyncpg.Pool, key: str,
) -> tuple[float | None, float | None]:
    p = await get(pool, key)
    if p is None:
        raise ParameterError(f"parametre inconnu : {key}")
    return (float(p.allowed_min) if p.allowed_min is not None else None,
            float(p.allowed_max) if p.allowed_max is not None else None)
