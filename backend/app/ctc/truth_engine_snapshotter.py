"""V5.3 BLOC 18 - Truth Engine Snapshotter.

Snapshots meta chaque 6h (metadata only ici, dump physique optionnel).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import asyncpg

from app.ctc import evidence_chain

TABLES_TO_SNAPSHOT = [
    "truth_sources", "truth_assertions", "truth_assertion_links",
    "evidence_chain_events", "phase_gates", "phase_gate_failures",
    "human_overrides", "meta_truth_audits", "truth_chaos_runs",
]


async def create_snapshot(
    pool: asyncpg.Pool, storage_path: str = "/tmp/ctc_snapshots",
) -> dict[str, Any]:
    # Chain integrity check first
    report = await evidence_chain.verify_chain(pool, limit=10_000)
    async with pool.acquire() as conn:
        # Collect rowcounts
        counts: dict[str, int] = {}
        for t in TABLES_TO_SNAPSHOT:
            try:
                n = await conn.fetchval(f"SELECT COUNT(*) FROM {t}")
                counts[t] = int(n or 0)
            except Exception:
                counts[t] = -1
        checksum = hashlib.sha256(
            json.dumps(counts, sort_keys=True).encode()).hexdigest()
        row = await conn.fetchrow(
            """
            INSERT INTO truth_engine_snapshots(
                tables_included, storage_path, compressed_bytes,
                chain_integrity_ok, checksum)
            VALUES ($1::jsonb, $2, $3, $4, $5)
            RETURNING snapshot_id, created_at
            """,
            json.dumps(counts), storage_path[:500], 0,
            report.status == "preserved", checksum,
        )
    return {
        "snapshot_id": str(row["snapshot_id"]),
        "created_at": row["created_at"].isoformat(),
        "tables": counts, "chain_integrity": report.status,
        "checksum": checksum,
    }


async def list_snapshots(
    pool: asyncpg.Pool, limit: int = 10,
) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT snapshot_id, created_at, tables_included,
                   chain_integrity_ok, checksum, retention_until
            FROM truth_engine_snapshots
            ORDER BY created_at DESC LIMIT $1
            """, limit,
        )
    return [{
        "snapshot_id": str(r["snapshot_id"]),
        "created_at": r["created_at"].isoformat(),
        "tables": (json.loads(r["tables_included"])
                    if isinstance(r["tables_included"], str)
                    else r["tables_included"]),
        "chain_integrity_ok": r["chain_integrity_ok"],
        "checksum": r["checksum"],
        "retention_until": r["retention_until"].isoformat(),
    } for r in rows]
