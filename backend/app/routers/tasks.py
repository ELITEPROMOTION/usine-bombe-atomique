"""Endpoints taches de generation."""
import io
import zipfile
from uuid import UUID, uuid4

from arq.connections import RedisSettings, create_pool
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from app.config import get_settings
from app.database import get_pool
from app.orchestration import audit_events, evidence_ledger, policy_arbiter
from app.orchestration.contradiction_detector import detect as detect_contradictions
from app.orchestration.contradiction_detector import (
    format_question as format_contradiction_question,
)
from app.orchestration.cost_optimizer import estimate_tokens, select_model
from app.orchestration.escalator import Question, detect_question, record_question, resolve_question
from app.schemas import TaskCreate, TaskOut

router = APIRouter()


async def _enqueue_task(task_id: UUID) -> None:
    settings = get_settings()
    redis = await create_pool(RedisSettings(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        password=settings.REDIS_PASSWORD or None,
        database=settings.REDIS_DB,
    ))
    try:
        await redis.enqueue_job("run_task", str(task_id))
    finally:
        await redis.aclose()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate) -> TaskOut:
    pool = get_pool()

    # V4.1 PolicyArbiter (DENY prevaut, aucun LLM consomme)
    selection = select_model(payload.prompt, payload.priority)
    arbiter_req = policy_arbiter.ArbiterRequest(
        spec=payload.prompt,
        priority=payload.priority,
        estimated_cost_usd=selection.estimated_cost_usd,
        budget_cap_usd=2.0,
        has_validated_artifacts=False,
        is_deploy_request=False,
        evidences_incomplete=False,
    )
    decision = policy_arbiter.evaluate(arbiter_req)
    await evidence_ledger.record(
        pool, kind="arbiter", actor="policy_arbiter",
        payload={"rule_id": decision.rule_id, "allow": decision.allow,
                 "rationale": decision.rationale, "signals": decision.signals,
                 "priority": payload.priority,
                 "estimated_cost_usd": selection.estimated_cost_usd},
    )
    if not decision.allow:
        raise HTTPException(422, {"arbiter_deny": decision.rule_id,
                                   "rationale": decision.rationale})

    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, tenant_id FROM users LIMIT 1",
        )
        if not user:
            raise HTTPException(400, "No user in DB - register first")
        user_id = user["id"]
        tenant_id = user["tenant_id"]

        session_id = payload.session_id
        if session_id is None:
            session_id = uuid4()
            await conn.execute(
                "INSERT INTO sessions (id, user_id, title, tenant_id) "
                "VALUES ($1, $2, $3, $4)",
                session_id, user_id, payload.prompt[:100], tenant_id,
            )

        row = await conn.fetchrow(
            """
            INSERT INTO tasks (id, session_id, user_id, prompt, priority, tenant_id)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, session_id, user_id, prompt, status, priority,
                      validation_score, rework_count, created_at, updated_at
            """,
            uuid4(), session_id, user_id, payload.prompt, payload.priority, tenant_id,
        )

    await audit_events.emit(
        pool, action="task_created", actor=f"user:{user_id}",
        payload={"prompt_excerpt": payload.prompt[:200], "priority": payload.priority,
                 "estimated_tokens": estimate_tokens(payload.prompt)},
        task_id=str(row["id"]), tenant_id=str(tenant_id),
    )

    # V4.1 Contradiction detector -> escalade E3 si contradiction
    contradictions = detect_contradictions(payload.prompt)
    if contradictions:
        q = Question(
            category="contradiction_detected",
            question=format_contradiction_question(contradictions),
            evidence={"contradictions": [
                {"rule": c.rule, "a": c.side_a, "b": c.side_b}
                for c in contradictions
            ]},
        )
        await record_question(pool, str(row["id"]), q)
        await evidence_ledger.record(
            pool, kind="contradiction", actor="contradiction_detector",
            payload={"rules": [c.rule for c in contradictions]},
            task_id=str(row["id"]),
        )
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, session_id, user_id, prompt, status, priority,
                   validation_score, rework_count, created_at, updated_at
                   FROM tasks WHERE id = $1""",
                row["id"],
            )
        return TaskOut(**dict(row))

    # V4 escalator (spec courte, DZ sans constantes, multi-domaine, etc.)
    question = detect_question(payload.prompt, payload.priority)
    if question:
        await record_question(pool, str(row["id"]), question)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT id, session_id, user_id, prompt, status, priority,
                   validation_score, rework_count, created_at, updated_at
                   FROM tasks WHERE id = $1""",
                row["id"],
            )
    else:
        await _enqueue_task(row["id"])
    return TaskOut(**dict(row))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: UUID) -> TaskOut:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, session_id, user_id, prompt, status, priority,
                   validation_score, rework_count, created_at, updated_at
            FROM tasks WHERE id = $1
            """,
            task_id,
        )
    if not row:
        raise HTTPException(404, "Task not found")
    return TaskOut(**dict(row))


@router.get("", response_model=list[TaskOut])
async def list_tasks(limit: int = 50) -> list[TaskOut]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, session_id, user_id, prompt, status, priority,
                   validation_score, rework_count, created_at, updated_at
            FROM tasks ORDER BY created_at DESC LIMIT $1
            """,
            limit,
        )
    return [TaskOut(**dict(r)) for r in rows]


@router.get("/{task_id}/executions")
async def list_executions(task_id: UUID) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, agent_id, agent_name, status, duration_ms,
                   output_json, error_message, started_at, completed_at
            FROM agent_executions
            WHERE task_id = $1
            ORDER BY agent_id
            """,
            task_id,
        )
    return [
        {
            "id": str(r["id"]),
            "agent_id": r["agent_id"],
            "agent_name": r["agent_name"],
            "status": r["status"],
            "duration_ms": float(r["duration_ms"]) if r["duration_ms"] is not None else None,
            "output": r["output_json"],
            "error": r["error_message"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "completed_at": r["completed_at"].isoformat() if r["completed_at"] else None,
        }
        for r in rows
    ]


@router.get("/{task_id}/confidence")
async def get_confidence(task_id: UUID) -> dict:
    import json as _json
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT plan_json FROM tasks WHERE id = $1", task_id,
        )
    if not row:
        raise HTTPException(404, "Task not found")
    plan = row["plan_json"]
    if isinstance(plan, str):
        try:
            plan = _json.loads(plan)
        except _json.JSONDecodeError:
            plan = {}
    plan = plan or {}
    confidence = plan.get("confidence") if isinstance(plan, dict) else None
    if not confidence:
        raise HTTPException(404, "No confidence report yet")
    return confidence


@router.get("/{task_id}/validation")
async def get_validation(task_id: UUID) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT level_number, level_name, score, passed, details, issues_json
            FROM validation_logs
            WHERE task_id = $1
            ORDER BY level_number
            """,
            task_id,
        )
    return [
        {
            "level": r["level_number"],
            "name": r["level_name"],
            "score": float(r["score"]),
            "passed": r["passed"],
            "details": r["details"],
            "issues": r["issues_json"] or [],
        }
        for r in rows
    ]


@router.get("/{task_id}/artifacts")
async def list_artifacts(task_id: UUID) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, filename, path, type, language, size_bytes, checksum_sha256
            FROM artifacts
            WHERE task_id = $1
            ORDER BY path
            """,
            task_id,
        )
    return [
        {
            "id": str(r["id"]),
            "filename": r["filename"],
            "path": r["path"],
            "type": r["type"],
            "language": r["language"],
            "size_bytes": r["size_bytes"],
            "checksum": r["checksum_sha256"],
        }
        for r in rows
    ]


@router.get("/{task_id}/artifacts/{artifact_id}")
async def get_artifact(task_id: UUID, artifact_id: UUID) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, path, language, type, size_bytes, content
            FROM artifacts WHERE id = $1 AND task_id = $2
            """,
            artifact_id, task_id,
        )
    if not row:
        raise HTTPException(404, "Artifact not found")
    return {
        "id": str(row["id"]),
        "path": row["path"],
        "language": row["language"],
        "type": row["type"],
        "size_bytes": row["size_bytes"],
        "content": row["content"] or "",
    }


@router.get("/{task_id}/artifacts/{artifact_id}/download")
async def download_artifact(task_id: UUID, artifact_id: UUID) -> Response:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT filename, content FROM artifacts WHERE id=$1 AND task_id=$2",
            artifact_id, task_id,
        )
    if not row:
        raise HTTPException(404, "Artifact not found")
    return Response(
        content=(row["content"] or "").encode("utf-8"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{row["filename"]}"'},
    )


@router.post("/{task_id}/answer")
async def answer_question(task_id: UUID, payload: dict) -> dict:
    """V4 : reponse a la question d'escalade - ajoute au prompt et re-enqueue."""
    answer = (payload or {}).get("answer", "").strip()
    if not answer:
        raise HTTPException(400, "answer required")
    pool = get_pool()
    ok = await resolve_question(pool, str(task_id), answer)
    if not ok:
        raise HTTPException(404, "No open question for this task")
    await _enqueue_task(task_id)
    return {"ok": True, "task_id": str(task_id), "re_enqueued": True}


@router.get("/{task_id}/download")
async def download_task_zip(task_id: UUID) -> StreamingResponse:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT path, content FROM artifacts WHERE task_id=$1 ORDER BY path",
            task_id,
        )
    if not rows:
        raise HTTPException(404, "No artifacts for this task")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in rows:
            zf.writestr(r["path"], r["content"] or "")
    buf.seek(0)

    short = str(task_id)[:8]
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="uba-{short}.zip"'},
    )
