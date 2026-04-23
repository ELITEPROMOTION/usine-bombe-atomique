import logging
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from app.models import Paiement, StatutPaiement

logger = logging.getLogger(__name__)

PALIERS_POURCENTAGES: list[int] = [20, 15, 35, 25, 5]
TWO_PLACES = Decimal("0.01")


def valider_nin(nin: str) -> bool:
    """Valide qu'un NIN algerien est compose de 18 chiffres."""
    return isinstance(nin, str) and nin.isdigit() and len(nin) == 18


def calculer_tva(prix_ht: Decimal) -> Decimal:
    """Calcule la TVA a 19%."""
    return (prix_ht * Decimal("0.19")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculer_tap(prix_ht: Decimal) -> Decimal:
    """Calcule la TAP a 2%."""
    return (prix_ht * Decimal("0.02")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def calculer_prix_ttc(prix_ht: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Retourne (tva_19pct, tap_2pct, prix_ttc)."""
    tva = calculer_tva(prix_ht)
    tap = calculer_tap(prix_ht)
    ttc = (prix_ht + tva + tap).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    logger.debug(
        "Calcul fiscal: HT=%s TVA=%s TAP=%s TTC=%s", prix_ht, tva, tap, ttc
    )
    return tva, tap, ttc


def generer_echeancier(
    reservation_id: int,
    prix_ttc: Decimal,
    date_debut: datetime,
    id_start: int = 1,
) -> list[Paiement]:
    """Genere les 5 paliers de paiement VEFA."""
    paiements: list[Paiement] = []
    cumul = Decimal("0.00")
    n = len(PALIERS_POURCENTAGES)

    for i, pct in enumerate(PALIERS_POURCENTAGES):
        palier_num = i + 1
        date_echeance = date_debut + timedelta(days=30 * i)

        if palier_num == n:
            # Dernier palier : ajustement pour eviter les erreurs d'arrondi
            montant = (prix_ttc - cumul).quantize(
                TWO_PLACES, rounding=ROUND_HALF_UP
            )
        else:
            montant = (
                prix_ttc * Decimal(pct) / Decimal("100")
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            cumul += montant

        paiement = Paiement(
            id=id_start + i,
            reservation_id=reservation_id,
            palier=palier_num,
            pourcentage=pct,
            montant_du=montant,
            montant_paye=Decimal("0.00"),
            date_echeance=date_echeance,
            statut=StatutPaiement.a_venir,
        )
        paiements.append(paiement)
        logger.debug(
            "Palier %s: %s%% -> %s DZD, echeance %s",
            palier_num,
            pct,
            montant,
            date_echeance.date(),
        )

    return paiements
