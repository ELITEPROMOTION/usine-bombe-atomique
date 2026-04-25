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
    domains,
    features,
    health,
    intelligence,
    observability,
    projects,
    provisioning,
    resilience,
    slo,
    tasks,
    truth,
    websocket,
    workflows,
)
from app.health.router import router as health_v2_router
from app.observability import otel_setup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    await init_pool()
    logger.info("DB pool initialized")
    # V5.6 : register 5 domains + load YAML rules
    try:
        from app.domains import register_all
        register_all()
        logger.info("V5.6 domains registered")
    except Exception as exc:
        logger.warning("V5.6 domains registration failed: %s", exc)
    # V5.9 : OpenTelemetry (best-effort, no-op if SDK absent)
    try:
        otel_status = otel_setup.init_otel(app=app)
        logger.info("V5.9 OTel: %s", otel_status)
    except Exception as exc:
        logger.warning("V5.9 OTel init failed: %s", exc)
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
app.include_router(domains.router, prefix=f"{settings.API_PREFIX}", tags=["domains_v5_6"])
app.include_router(features.router, prefix=f"{settings.API_PREFIX}", tags=["features_v5_6"])
app.include_router(resilience.router, prefix=f"{settings.API_PREFIX}", tags=["resilience_v5_7"])
app.include_router(slo.router, prefix=f"{settings.API_PREFIX}", tags=["slo_v5_7"])
app.include_router(health_v2_router, prefix=f"{settings.API_PREFIX}", tags=["health_v5_7"])
app.include_router(intelligence.router, prefix=f"{settings.API_PREFIX}", tags=["intelligence_v5_8"])
app.include_router(observability.router, prefix=f"{settings.API_PREFIX}", tags=["observability_v5_9"])
app.include_router(projects.router, prefix=f"{settings.API_PREFIX}/projects", tags=["projects_v7"])
app.include_router(websocket.router, tags=["ws"])
