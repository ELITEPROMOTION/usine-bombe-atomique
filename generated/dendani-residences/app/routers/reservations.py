import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.business import calculer_prix_ttc, generer_echeancier
from app.models import Echeancier, Paiement, Reservation, ReservationCreate, StatutReservation
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reservations", tags=["Reservations"])


@router.post("", response_model=Reservation, status_code=201)
def create_reservation(payload: ReservationCreate) -> Reservation:
    """Cree une reservation VEFA et genere automatiquement l'echeancier de 5 paliers."""
    client = store.get_client(payload.client_id)
    if client is None:
        raise HTTPException(
            status_code=404,
            detail=f"Client {payload.client_id} introuvable",
        )

    tva, tap, ttc = calculer_prix_ttc(payload.prix_ht)
    date_resa = payload.date_reservation or datetime.now(tz=timezone.utc)

    new_reservation = Reservation(
        id=store.next_reservation_id(),
        client_id=payload.client_id,
        residence_nom=payload.residence_nom,
        num_lot=payload.num_lot,
        prix_ht=payload.prix_ht,
        tva_19pct=tva,
        tap_2pct=tap,
        prix_ttc=ttc,
        date_reservation=date_resa,
        statut=StatutReservation.active,
    )
    reservation = store.create_reservation(new_reservation)

    paliers: list[Paiement] = generer_echeancier(
        reservation_id=reservation.id,
        prix_ttc=ttc,
        date_debut=date_resa,
    )
    for palier in paliers:
        store.create_paiement(palier)

    logger.info(
        "Reservation creee: id=%s residence=%s lot=%s",
        reservation.id,
        reservation.residence_nom,
        reservation.num_lot,
    )
    return reservation


@router.get("/{reservation_id}", response_model=Reservation)
def get_reservation(reservation_id: int) -> Reservation:
    """Retourne une reservation par son identifiant."""
    reservation = store.get_reservation(reservation_id)
    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reservation {reservation_id} introuvable",
        )
    return reservation


@router.get("/{reservation_id}/echeancier", response_model=Echeancier)
def get_echeancier(reservation_id: int) -> Echeancier:
    """Retourne l'echeancier complet d'une reservation."""
    reservation = store.get_reservation(reservation_id)
    if reservation is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reservation {reservation_id} introuvable",
        )
    paiements = store.get_paiements_by_reservation(reservation_id)
    paiements_tries = sorted(paiements, key=lambda p: p.palier)
    return Echeancier(reservation_id=reservation_id, paiements=paiements_tries)
