import logging

from fastapi import APIRouter, HTTPException

from app.models import Paiement, StatutPaiement
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/paiements", tags=["Paiements"])


@router.post("/{paiement_id}/regler", response_model=Paiement)
def regler_paiement(paiement_id: int) -> Paiement:
    """Regle un paiement : met montant_paye = montant_du et statut = paye."""
    paiement = store.get_paiement(paiement_id)
    if paiement is None:
        raise HTTPException(
            status_code=404,
            detail=f"Paiement {paiement_id} introuvable",
        )
    if paiement.statut == StatutPaiement.paye:
        raise HTTPException(
            status_code=400,
            detail=f"Paiement {paiement_id} est deja regle",
        )

    updated = paiement.model_copy(
        update={
            "montant_paye": paiement.montant_du,
            "statut": StatutPaiement.paye,
        }
    )
    store.update_paiement(paiement_id, updated)
    logger.info(
        "Paiement regle: id=%s reservation_id=%s palier=%s montant=%s",
        paiement_id,
        paiement.reservation_id,
        paiement.palier,
        paiement.montant_du,
    )
    return updated
