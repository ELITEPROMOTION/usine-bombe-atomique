"""Endpoint de sante."""
from fastapi import APIRouter

from app.config import get_settings
from app.database import get_pool
from app.schemas import HealthResponse

router = APIRouter()
settings = get_settings()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    db_ok = False
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False

    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=settings.APP_VERSION,
        db=db_ok,
        redis=True,
    )
