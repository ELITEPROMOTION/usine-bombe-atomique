import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models import Client, ClientCreate, ClientUpdate
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("", response_model=Client, status_code=201)
def create_client(payload: ClientCreate) -> Client:
    """Cree un nouveau client."""
    new_client = Client(
        id=store.next_client_id(),
        nom=payload.nom,
        prenom=payload.prenom,
        nin=payload.nin,
        telephone=payload.telephone,
        email=payload.email,
        adresse=payload.adresse,
        created_at=datetime.now(tz=timezone.utc),
    )
    client = store.create_client(new_client)
    logger.info("Client cree: id=%s nom=%s %s", client.id, client.nom, client.prenom)
    return client


@router.get("", response_model=list[Client])
def list_clients() -> list[Client]:
    """Liste tous les clients."""
    return store.get_all_clients()


@router.get("/{client_id}", response_model=Client)
def get_client(client_id: int) -> Client:
    """Retourne un client par son identifiant."""
    client = store.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Client {client_id} introuvable")
    return client


@router.put("/{client_id}", response_model=Client)
def update_client(client_id: int, payload: ClientUpdate) -> Client:
    """Met a jour les informations d'un client."""
    client = store.get_client(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail=f"Client {client_id} introuvable")

    updated_data = client.model_dump()
    patch = payload.model_dump(exclude_none=True)
    updated_data.update(patch)

    updated_client = Client(**updated_data)
    store.update_client(client_id, updated_client)
    logger.info("Client mis a jour: id=%s", client_id)
    return updated_client


@router.delete("/{client_id}", status_code=204)
def delete_client(client_id: int) -> None:
    """Supprime un client."""
    deleted = store.delete_client(client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Client {client_id} introuvable")
    logger.info("Client supprime: id=%s", client_id)
