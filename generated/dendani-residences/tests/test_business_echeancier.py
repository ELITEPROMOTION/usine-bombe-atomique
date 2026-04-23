from datetime import datetime, timezone
from decimal import Decimal

from app.business import generer_echeancier, PALIERS_POURCENTAGES


PRIX_TTC = Decimal("12100000.00")
DATE_DEBUT = datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_echeancier_5_paliers() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    assert len(paliers) == 5


def test_echeancier_somme_pourcentages_100() -> None:
    assert sum(PALIERS_POURCENTAGES) == 100


def test_echeancier_pourcentages_corrects() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    pourcentages = [p.pourcentage for p in paliers]
    assert pourcentages == [20, 15, 35, 25, 5]


def test_echeancier_montants_corrects() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    assert paliers[0].montant_du == Decimal("2420000.00")  # 20%
    assert paliers[1].montant_du == Decimal("1815000.00")  # 15%
    assert paliers[2].montant_du == Decimal("4235000.00")  # 35%
    assert paliers[3].montant_du == Decimal("3025000.00")  # 25%


def test_echeancier_somme_montants_egal_ttc() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    total = sum(p.montant_du for p in paliers)
    assert total == PRIX_TTC


def test_echeancier_echeances_espacees_30_jours() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    for i in range(1, len(paliers)):
        delta = paliers[i].date_echeance - paliers[i - 1].date_echeance
        assert delta.days == 30


def test_echeancier_reservation_id_correct() -> None:
    paliers = generer_echeancier(42, PRIX_TTC, DATE_DEBUT)
    for p in paliers:
        assert p.reservation_id == 42


def test_echeancier_montant_paye_defaut_zero() -> None:
    paliers = generer_echeancier(1, PRIX_TTC, DATE_DEBUT)
    for p in paliers:
        assert p.montant_paye == Decimal("0.00")
