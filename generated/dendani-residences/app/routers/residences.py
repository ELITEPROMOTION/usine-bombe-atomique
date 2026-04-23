import logging

from fastapi import APIRouter, HTTPException

from app.models import Residence, ResidenceNom
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/residences", tags=["Residences"])


@router.get("", response_model=list[Residence])
def list_residences() -> list[Residence]:
    """Liste toutes les residences du Groupe Dendani."""
    return store.get_all_residences()


@router.get("/{nom}", response_model=Residence)
def get_residence(nom: ResidenceNom) -> Residence:
    """Retourne le detail d'une residence par son nom."""
    residence = store.get_residence(nom)
    if residence is None:
        raise HTTPException(status_code=404, detail=f"Residence '{nom}' introuvable")
    return residence
