import logging
from decimal import Decimal

from fastapi import APIRouter

from app.models import RapportEncaissements, ResidenceEncaissement
from app.store import store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/encaissements", response_model=RapportEncaissements)
def rapport_encaissements() -> RapportEncaissements:
    """Retourne le rapport d'encaissements par residence."""
    reservations = store.get_all_reservations()
    paiements = store.get_all_paiements()

    paiements_par_resa: dict[int, list] = {}
    for p in paiements:
        paiements_par_resa.setdefault(p.reservation_id, []).append(p)

    encaissements_par_residence: dict[str, dict[str, Decimal]] = {}

    for resa in reservations:
        nom = resa.residence_nom.value
        if nom not in encaissements_par_residence:
            encaissements_par_residence[nom] = {
                "encaisse": Decimal("0.00"),
                "reste": Decimal("0.00"),
            }
        for p in paiements_par_resa.get(resa.id, []):
            encaissements_par_residence[nom]["encaisse"] += p.montant_paye
            encaissements_par_residence[nom]["reste"] += (
                p.montant_du - p.montant_paye
            )

    residences_data: list[ResidenceEncaissement] = [
        ResidenceEncaissement(
            residence_nom=nom,
            total_encaisse=vals["encaisse"],
            total_reste=vals["reste"],
        )
        for nom, vals in encaissements_par_residence.items()
    ]

    total_encaisse = sum(
        (r.total_encaisse for r in residences_data), Decimal("0.00")
    )
    total_reste = sum(
        (r.total_reste for r in residences_data), Decimal("0.00")
    )

    logger.info(
        "Rapport encaissements: total_encaisse=%s total_reste=%s",
        total_encaisse,
        total_reste,
    )
    return RapportEncaissements(
        residences=residences_data,
        total_global_encaisse=total_encaisse,
        total_global_reste=total_reste,
    )
