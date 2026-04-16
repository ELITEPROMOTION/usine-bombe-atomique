"""Endpoints taches de generation."""
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from app.database import get_pool
from app.schemas import TaskCreate, TaskOut

router = APIRouter()


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate) -> TaskOut:
    pool = get_pool()
    async with pool.acquire() as conn:
        # Bootstrap stub: user fixe "bootstrap-user" si absent
        user = await conn.fetchrow("SELECT id FROM users LIMIT 1")
        if not user:
            raise HTTPException(400, "No user in DB - register first")
        user_id = user["id"]

        session_id = payload.session_id
        if session_id is None:
            session_id = uuid4()
            await conn.execute(
                "INSERT INTO sessions (id, user_id, title) VALUES ($1, $2, $3)",
                session_id, user_id, payload.prompt[:100],
            )

        row = await conn.fetchrow(
            """
            INSERT INTO tasks (id, session_id, user_id, prompt, priority)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id, session_id, user_id, prompt, status, priority,
                      validation_score, rework_count, created_at, updated_at
            """,
            uuid4(), session_id, user_id, payload.prompt, payload.priority,
        )
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
