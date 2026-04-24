"""Point d'entree FastAPI avec lifespan manager."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import close_pool, init_pool
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.tenant import TenantMiddleware
from app.routers import (
    ahmed_inbox,
    analytics,
    auth,
    autonomy,
    cognition,
    dehardcoding,
    health,
    provisioning,
    tasks,
    truth,
    websocket,
    workflows,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_pool()
    logger.info("DB pool initialized")
    yield
    await close_pool()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)
app.add_middleware(TenantMiddleware)

app.include_router(health.router, prefix=settings.API_PREFIX, tags=["health"])
app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["auth"])
app.include_router(tasks.router, prefix=f"{settings.API_PREFIX}/tasks", tags=["tasks"])
app.include_router(analytics.router, prefix=f"{settings.API_PREFIX}/analytics", tags=["analytics"])
app.include_router(provisioning.router, prefix=f"{settings.API_PREFIX}", tags=["provisioning"])
app.include_router(ahmed_inbox.router, prefix=f"{settings.API_PREFIX}", tags=["ahmed_inbox"])
app.include_router(autonomy.router, prefix=f"{settings.API_PREFIX}", tags=["autonomy_v5_1"])
app.include_router(dehardcoding.router, prefix=f"{settings.API_PREFIX}", tags=["dehardcoding_v5_2"])
app.include_router(truth.router, prefix=f"{settings.API_PREFIX}", tags=["ctc_v5_3"])
app.include_router(cognition.router, prefix=f"{settings.API_PREFIX}", tags=["cognition_v5_4"])
app.include_router(workflows.router, prefix=f"{settings.API_PREFIX}", tags=["automation_v5_5"])
app.include_router(websocket.router, tags=["ws"])
