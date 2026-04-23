"""Fixtures pytest communes."""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import close_pool, get_pool, init_pool
from app.main import app


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app),
                            base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def pool():
    """Pool asyncpg function-scoped (evite cross-event-loop sharing)."""
    from app.database import _pool as existing  # noqa: PLC0415
    if existing is not None:
        yield existing
        return
    p = await init_pool()
    try:
        yield p
    finally:
        await close_pool()


@pytest_asyncio.fixture
async def seeded_task_id(pool):
    """Cree une tache minimale. Pas de DELETE (audit_events append-only
    empeche les cascades UPDATE)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tasks(user_id, session_id, prompt, priority, status)
            VALUES (
              (SELECT id FROM users LIMIT 1),
              (SELECT id FROM sessions LIMIT 1),
              'test seed', 'medium', 'pending'
            ) RETURNING id
            """
        )
    yield str(row["id"])
