from decimal import Decimal

from app.business import calculer_tap, calculer_tva, calculer_prix_ttc


def test_tva_19pct_calcul_exact() -> None:
    prix_ht = Decimal("10000000.00")
    tva = calculer_tva(prix_ht)
    assert tva == Decimal("1900000.00")


def test_tap_2pct_calcul_exact() -> None:
    prix_ht = Decimal("10000000.00")
    tap = calculer_tap(prix_ht)
    assert tap == Decimal("200000.00")


def test_prix_ttc_calcul_exact() -> None:
    prix_ht = Decimal("10000000.00")
    tva, tap, ttc = calculer_prix_ttc(prix_ht)
    assert tva == Decimal("1900000.00")
    assert tap == Decimal("200000.00")
    assert ttc == Decimal("12100000.00")


def test_tva_arrondi() -> None:
    prix_ht = Decimal("333.33")
    tva = calculer_tva(prix_ht)
    assert tva == Decimal("63.33")


def test_tap_arrondi() -> None:
    prix_ht = Decimal("333.33")
    tap = calculer_tap(prix_ht)
    assert tap == Decimal("6.67")


def test_prix_ttc_composant() -> None:
    prix_ht = Decimal("5000000.00")
    tva, tap, ttc = calculer_prix_ttc(prix_ht)
    assert ttc == prix_ht + tva + tap
