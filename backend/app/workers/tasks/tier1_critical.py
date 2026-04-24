"""Tier 1 - Critical monitoring (toutes les 10-30 min).

Tasks :
  - task_queue_saturation_monitor
  - task_health_deep_check
  - task_truth_integrity_check
  - task_evidence_chain_verification
"""
from __future__ import annotations

import os
from typing import Any

from app.database import get_pool
from app.orchestration import audit_events, evidence_ledger

from ._base import logger, workflow_task


@workflow_task("task_queue_saturation_monitor", timeout_s=60)
async def task_queue_saturation_monitor(_ctx: dict[str, Any] | None = None,
                                         **_: Any) -> dict[str, Any]:
    """Mesure la saturation de la queue arq via Redis (ZCARD/LLEN arq:queue*)."""
    import redis.asyncio as redis_lib

    from app.config import get_settings
    settings = get_settings()
    r = redis_lib.Redis(
        host=settings.REDIS_HOST, port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None, db=settings.REDIS_DB,
    )
    try:
        queue_len = 0
        for key in ("arq:queue", "arq:queue:health-check"):
            ktype = await r.type(key)
            ktype_s = ktype.decode() if isinstance(ktype, bytes) else str(ktype)
            if ktype_s == "zset":
                queue_len = max(queue_len, int(await r.zcard(key)))
            elif ktype_s == "list":
                queue_len = max(queue_len, int(await r.llen(key)))
        try:
            inflight = int(await r.zcard("arq:in-progress"))
        except Exception:
            inflight = 0
    finally:
        try:
            await r.aclose()
        except Exception as exc:
            logger.debug("redis aclose failed: %s", exc)
    saturation = "ok" if queue_len < 100 else ("warn" if queue_len < 500 else "alert")
    return {
        "queue_len": queue_len,
        "inflight": inflight,
        "saturation": saturation,
        "threshold_warn": 100,
        "threshold_alert": 500,
    }


@workflow_task("task_health_deep_check", timeout_s=90)
async def task_health_deep_check(_ctx: dict[str, Any] | None = None,
                                  **_: Any) -> dict[str, Any]:
    """Ping postgres + redis + vault. Retourne rapport."""
    import httpx
    import redis.asyncio as redis_lib

    from app.config import get_settings
    settings = get_settings()
    report: dict[str, Any] = {"services": {}}

    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1")
        report["services"]["postgres"] = {"ok": val == 1}
    except Exception as exc:
        report["services"]["postgres"] = {"ok": False, "error": str(exc)}

    try:
        r = redis_lib.Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD or None, db=settings.REDIS_DB,
        )
        pong = await r.ping()
        await r.aclose()
        report["services"]["redis"] = {"ok": bool(pong)}
    except Exception as exc:
        report["services"]["redis"] = {"ok": False, "error": str(exc)}

    try:
        vault_addr = os.environ.get("VAULT_ADDR", "http://vault:8200")
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get(f"{vault_addr}/v1/sys/health?standbyok=true")
        report["services"]["vault"] = {"ok": resp.status_code in (200, 429)}
    except Exception as exc:
        report["services"]["vault"] = {"ok": False, "error": str(exc)[:200]}

    report["healthy"] = all(s.get("ok") for s in report["services"].values())
    return report


@workflow_task("task_truth_integrity_check", timeout_s=120)
async def task_truth_integrity_check(_ctx: dict[str, Any] | None = None,
                                      **_: Any) -> dict[str, Any]:
    """Verifie integrite de l'evidence_ledger (hash chain)."""
    pool = get_pool()
    rep = await evidence_ledger.verify_chain(pool, limit=20_000)
    return {
        "events_checked": int(rep.get("events_checked", 0)),
        "integrity_ok": bool(rep.get("integrity_ok", False)),
        "broken_count": len(rep.get("broken", [])),
    }


# Tables CTC whitelisted pour les queries COUNT(*)
_CTC_TABLES: tuple[str, ...] = (
    "ctc_assertions", "ctc_evidence_chain",
    "ctc_truth_graph", "ctc_human_overrides",
)


@workflow_task("task_evidence_chain_verification", timeout_s=120)
async def task_evidence_chain_verification(_ctx: dict[str, Any] | None = None,
                                            **_: Any) -> dict[str, Any]:
    """Audit CTC : chain recompute + compte tables + immutability audit.

    Optim : compte les 4 tables CTC en UNION ALL (N+1 -> 1 query).
    """
    pool = get_pool()
    report: dict[str, Any] = {}
    async with pool.acquire() as conn:
        evl = await conn.fetchval("SELECT COUNT(*) FROM evidence_ledger")
        report["evidence_ledger_count"] = int(evl)

        # N+1 fix : recupere les tables existantes en 1 query
        existing = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = ANY($1::text[])",
            list(_CTC_TABLES),
        )
        existing_names = {r["table_name"] for r in existing}
        if existing_names:
            union_parts = [
                f"SELECT '{t}' AS tbl, COUNT(*) AS n FROM {t}"
                for t in _CTC_TABLES
                if t in existing_names
            ]
            rows = await conn.fetch(" UNION ALL ".join(union_parts))
            for r in rows:
                report[r["tbl"]] = int(r["n"])
    chain = await evidence_ledger.verify_chain(pool, limit=20_000)
    report["integrity_ok"] = bool(chain.get("integrity_ok"))
    report["broken_count"] = len(chain.get("broken", []))
    report["audit_immutability"] = await audit_events.verify_immutability(pool)
    return report


ALL_TASKS = [
    task_queue_saturation_monitor,
    task_health_deep_check,
    task_truth_integrity_check,
    task_evidence_chain_verification,
]
