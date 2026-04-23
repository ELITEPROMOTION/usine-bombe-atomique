import logging

from fastapi import FastAPI

from app.models import HealthResponse
from app.routers import clients, paiements, reports, reservations, residences

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Dendani Residences API",
    description=(
        "API de gestion des clients et reservations VEFA "
        "pour le Groupe Dendani (Algerie)"
    ),
    version="1.0.0",
)

app.include_router(residences.router)
app.include_router(clients.router)
app.include_router(reservations.router)
app.include_router(paiements.router)
app.include_router(reports.router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check() -> HealthResponse:
    """Verifie l'etat de l'API."""
    return HealthResponse(status="ok", version="1.0.0")
