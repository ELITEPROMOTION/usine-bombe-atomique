"""Tier 6 - Veille regulatoire + contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.database import get_pool

from ._base import workflow_task


@workflow_task("task_regulatory_dz_poll", timeout_s=180)
async def task_regulatory_dz_poll(_ctx: dict[str, Any] | None = None,
                                   **_: Any) -> dict[str, Any]:
    """Consulte la table dz_rules (nombre d'entries)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name='dz_rules')",
        )
        if not exists:
            return {"found": False, "rules": 0}
        n = await conn.fetchval("SELECT COUNT(*) FROM dz_rules")
    return {"found": True, "rules": int(n)}


@workflow_task("task_browser_contract_verify", timeout_s=180)
async def task_browser_contract_verify(_ctx: dict[str, Any] | None = None,
                                        **_: Any) -> dict[str, Any]:
    """Verifie contrats agents (parse JSON)."""
    candidates = [
        Path("/app/app/agent_contracts"),
        Path("backend/app/agent_contracts"),
    ]
    contracts_dir = next((p for p in candidates if p.exists()), None)
    if contracts_dir is None:
        return {"found": False, "contracts": 0}
    valid = 0
    invalid = 0
    for f in contracts_dir.rglob("*.json"):
        try:
            json.loads(f.read_text(encoding="utf-8"))
            valid += 1
        except Exception:
            invalid += 1
    return {"found": True, "valid_contracts": valid, "invalid_contracts": invalid}


ALL_TASKS = [
    task_regulatory_dz_poll,
    task_browser_contract_verify,
]
