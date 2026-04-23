import pytest

from app.business import valider_nin


def test_nin_valide_18_chiffres() -> None:
    assert valider_nin("123456789012345678") is True


def test_nin_invalide_trop_court() -> None:
    assert valider_nin("12345678901234567") is False


def test_nin_invalide_trop_long() -> None:
    assert valider_nin("1234567890123456789") is False


def test_nin_invalide_avec_lettres() -> None:
    assert valider_nin("12345678901234567A") is False


def test_nin_invalide_vide() -> None:
    assert valider_nin("") is False


def test_nin_invalide_avec_espaces() -> None:
    assert valider_nin("123456789 12345678") is False


def test_nin_invalide_type_incorrect() -> None:
    assert valider_nin(123456789012345678) is False  # type: ignore[arg-type]
