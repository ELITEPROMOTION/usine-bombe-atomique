"""WebSocket : flux temps-reel de la progression d'une tache.

Simple polling BDD cote serveur (1 s) : on emet uniquement quand le
"hash" de la snapshot change, puis on ferme lorsque le statut est terminal.
Ca evite un pub/sub complet en V1 tout en donnant une UX temps-reel propre.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import get_pool

logger = logging.getLogger(__name__)
router = APIRouter()

TERMINAL = {"completed", "failed", "cancelled"}


async def _snapshot(task_id: UUID) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow(
            """
            SELECT id, status, validation_score, rework_count,
                   started_at, completed_at, updated_at
            FROM tasks WHERE id = $1
            """,
            task_id,
        )
        if not task:
            return {"error": "not_found"}
        agents = await conn.fetch(
            """
            SELECT agent_id, agent_name, status, duration_ms
            FROM agent_executions WHERE task_id = $1 ORDER BY agent_id
            """,
            task_id,
        )
        validations = await conn.fetch(
            """
            SELECT level_number, level_name, score, passed
            FROM validation_logs WHERE task_id = $1 ORDER BY level_number
            """,
            task_id,
        )
        artifacts_count = await conn.fetchval(
            "SELECT COUNT(*) FROM artifacts WHERE task_id = $1", task_id,
        )
    return {
        "task": {
            "id": str(task["id"]),
            "status": task["status"],
            "validation_score": float(task["validation_score"] or 0),
            "rework_count": task["rework_count"],
            "started_at": task["started_at"].isoformat() if task["started_at"] else None,
            "completed_at": task["completed_at"].isoformat() if task["completed_at"] else None,
        },
        "agents": [
            {
                "agent_id": a["agent_id"],
                "agent_name": a["agent_name"],
                "status": a["status"],
                "duration_ms": float(a["duration_ms"]) if a["duration_ms"] else None,
            }
            for a in agents
        ],
        "validation": [
            {
                "level": v["level_number"],
                "name": v["level_name"],
                "score": float(v["score"]),
                "passed": v["passed"],
            }
            for v in validations
        ],
        "artifacts_count": int(artifacts_count or 0),
    }


def _fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()


@router.websocket("/ws/tasks/{task_id}")
async def task_stream(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        uuid = UUID(task_id)
    except ValueError:
        await websocket.send_json({"type": "error", "error": "bad_uuid"})
        await websocket.close()
        return

    last_fp = ""
    try:
        await websocket.send_json({"type": "connected", "task_id": task_id})
        while True:
            snap = await _snapshot(uuid)
            if "error" in snap:
                await websocket.send_json({"type": "error", "error": snap["error"]})
                break
            fp = _fingerprint(snap)
            if fp != last_fp:
                last_fp = fp
                await websocket.send_json({"type": "snapshot", **snap})
            if snap["task"]["status"] in TERMINAL:
                await websocket.send_json({"type": "done", "status": snap["task"]["status"]})
                break
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.exception("ws task_stream failed")
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        finally:
            pass
    finally:
        with contextlib.suppress(Exception):
            await websocket.close()
