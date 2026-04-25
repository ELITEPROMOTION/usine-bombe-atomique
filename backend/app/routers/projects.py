"""V7 Projects — pipeline 'CDC -> deliverable'.

Wrapper mince au-dessus du systeme tasks existant :
  POST   /api/v1/projects/from_cdc            -> cree une task avec prompt=cdc_text
  GET    /api/v1/projects/{project_id}/status -> status agrege (intake|executing|delivered|failed)
  GET    /api/v1/projects/{project_id}/deliverable -> ZIP des artifacts

Le project_id est l'UUID de la task sous-jacente.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any
from uuid import UUID, uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.database import get_pool
from app.orchestration import audit_events, evidence_ledger

router = APIRouter()


# -------- Schemas


class ProjectFromCDCRequest(BaseModel):
    cdc_text: str = Field(..., min_length=100, max_length=50_000)
    project_name: str = Field(..., min_length=1, max_length=120)
    tenant_id: str | None = None
    auto_resolve_ambiguities: bool = True
    max_duration_minutes: int = Field(default=30, ge=1, le=120)


class ProjectFromCDCResponse(BaseModel):
    project_id: str
    status: str
    estimated_duration_minutes: int


class ProjectStatusResponse(BaseModel):
    project_id: str
    project_name: str
    status: str
    progress_percent: int
    current_task: str
    tasks_completed: int
    tasks_total: int
    estimated_remaining_minutes: int
    deliverable_url: str | None = None
    error: str | None = None


# -------- Helpers


_TASK_STATUS_TO_PROJECT = {
    "pending": "intake",
    "queued": "intake",
    "running": "executing",
    "validating": "validating",
    "blocked": "clarifying",
    "completed": "delivered",
    "failed": "failed",
}


def _project_status(task_status: str) -> str:
    return _TASK_STATUS_TO_PROJECT.get(task_status, task_status or "intake")


async def _enqueue_task(task_id: UUID) -> None:
    settings = get_settings()
    redis = await create_pool(RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        database=settings.REDIS_DB,
    ))
    try:
        await redis.enqueue_job("run_task", str(task_id), _queue_name="uba:run_task")
    finally:
        await redis.aclose()


def _build_prompt(payload: ProjectFromCDCRequest) -> str:
    parts = [
        f"# Projet : {payload.project_name}",
        "",
        "## Cahier des charges",
        "",
        payload.cdc_text.strip(),
        "",
        "## Directives V7",
        "",
        f"- Nom de projet (identifiant slug) : {payload.project_name}",
        f"- Auto-resolve ambiguites : {payload.auto_resolve_ambiguities}",
        f"- Duree max : {payload.max_duration_minutes} min",
        "- Stack par defaut : FastAPI + PostgreSQL + Docker",
        "- Livrable : code complet + Dockerfile + docker-compose.yml + tests pytest",
        "- Le livrable DOIT etre buildable via `docker build .` apres extraction",
    ]
    return "\n".join(parts)


# -------- Endpoints


@router.post("/from_cdc", response_model=ProjectFromCDCResponse, status_code=201)
async def create_project_from_cdc(payload: ProjectFromCDCRequest) -> ProjectFromCDCResponse:
    pool = get_pool()
    prompt = _build_prompt(payload)

    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, tenant_id FROM users LIMIT 1")
        if not user:
            raise HTTPException(400, "No user in DB - register first")

        session_id = uuid4()
        await conn.execute(
            "INSERT INTO sessions (id, user_id, title, tenant_id) VALUES ($1, $2, $3, $4)",
            session_id, user["id"], payload.project_name[:100], user["tenant_id"],
        )

        row = await conn.fetchrow(
            """
            INSERT INTO tasks (id, session_id, user_id, prompt, priority, tenant_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, status
            """,
            uuid4(), session_id, user["id"], prompt, "high", user["tenant_id"],
        )

    project_id = str(row["id"])

    await audit_events.emit(
        pool, action="project_created", actor=f"user:{user['id']}",
        payload={
            "project_name": payload.project_name,
            "cdc_length": len(payload.cdc_text),
            "auto_resolve": payload.auto_resolve_ambiguities,
            "max_duration_minutes": payload.max_duration_minutes,
        },
        task_id=project_id, tenant_id=str(user["tenant_id"]),
    )
    await evidence_ledger.record(
        pool, kind="decision", actor="projects.from_cdc",
        payload={"project_name": payload.project_name, "stage": "submitted"},
        task_id=project_id,
    )

    await _enqueue_task(row["id"])

    return ProjectFromCDCResponse(
        project_id=project_id,
        status="intake",
        estimated_duration_minutes=min(payload.max_duration_minutes, 30),
    )


@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
async def get_project_status(project_id: UUID) -> ProjectStatusResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT id, status, prompt FROM tasks WHERE id = $1", project_id,
        )
        if not task:
            raise HTTPException(404, "Project not found")

        execs = await conn.fetch(
            """
            SELECT agent_id, agent_name, status
            FROM agent_executions
            WHERE task_id = $1
            ORDER BY agent_id ASC
            """,
            project_id,
        )
        artifacts_count = await conn.fetchval(
            "SELECT COUNT(*) FROM artifacts WHERE task_id = $1", project_id,
        )

    project_status = _project_status(task["status"])
    total = max(len(execs), 1)
    completed = sum(1 for e in execs if e["status"] in ("completed", "succeeded", "passed"))
    failed = sum(1 for e in execs if e["status"] in ("failed", "error"))

    if project_status == "delivered":
        progress = 100
    elif project_status == "failed":
        progress = 100
    else:
        progress = min(95, int((completed / total) * 95)) if total else 5

    current = next(
        (e["agent_name"] for e in execs if e["status"] in ("running", "in_progress")),
        execs[-1]["agent_name"] if execs else "intake",
    )

    project_name = task["prompt"].split("\n", 1)[0].replace("# Projet :", "").strip() or "untitled"
    deliverable_url = f"/api/v1/projects/{project_id}/deliverable" if project_status == "delivered" and artifacts_count else None
    error_msg: str | None = None
    if project_status == "failed":
        error_msg = f"{failed} agent execution(s) failed; check /api/v1/tasks/{project_id}/executions"

    return ProjectStatusResponse(
        project_id=str(project_id),
        project_name=project_name,
        status=project_status,
        progress_percent=progress,
        current_task=current,
        tasks_completed=completed,
        tasks_total=total,
        estimated_remaining_minutes=max(0, 30 - int(progress * 0.3)),
        deliverable_url=deliverable_url,
        error=error_msg,
    )


@router.get("/{project_id}/deliverable")
async def download_project_deliverable(project_id: UUID) -> StreamingResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        task = await conn.fetchrow(
            "SELECT status FROM tasks WHERE id = $1", project_id,
        )
        if not task:
            raise HTTPException(404, "Project not found")
        if task["status"] != "completed":
            raise HTTPException(404, f"Project not delivered yet (status={task['status']})")

        artifacts = await conn.fetch(
            "SELECT path, content FROM artifacts WHERE task_id = $1 ORDER BY path",
            project_id,
        )

    if not artifacts:
        raise HTTPException(404, "No artifacts on delivered project")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for a in artifacts:
            zf.writestr(a["path"], a["content"] or "")
    buf.seek(0)

    short = str(project_id)[:8]
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="uba-project-{short}.zip"'},
    )


@router.get("", response_model=list[dict[str, Any]])
async def list_projects(limit: int = 20) -> list[dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, prompt, status, priority, created_at, updated_at
            FROM tasks
            WHERE prompt LIKE '# Projet :%'
            ORDER BY created_at DESC
            LIMIT $1
            """,
            limit,
        )
    return [
        {
            "project_id": str(r["id"]),
            "project_name": r["prompt"].split("\n", 1)[0].replace("# Projet :", "").strip(),
            "status": _project_status(r["status"]),
            "priority": r["priority"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        }
        for r in rows
    ]
