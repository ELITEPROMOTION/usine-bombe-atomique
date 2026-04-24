"""Tests domaine comptabilite (30 tests)."""
from __future__ import annotations

import pytest

from .conftest import make_ctx

pytestmark = pytest.mark.asyncio


# ============================================================================
# Classe comptes - 10 tests
# ============================================================================

@pytest.mark.parametrize("numero,attendu_classe,attendu_categorie", [
    (101, 1, "capitaux"),
    (211, 2, "immobilisations"),
    (301, 3, "stocks"),
    (411, 4, "tiers"),
    (512, 5, "financiers"),
    (601, 6, "charges"),
    (701, 7, "produits"),
])
async def test_classe_compte(registry, numero, attendu_classe,
                                 attendu_categorie) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"numero_compte": numero}, make_ctx("comptabilite"),
    )
    assert res.output["classe"] == attendu_classe
    assert res.output["categorie"] == attendu_categorie


async def test_compte_max_bound_199(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"numero_compte": 199}, make_ctx("comptabilite"),
    )
    assert res.output["classe"] == 1


async def test_compte_bound_200(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"numero_compte": 200}, make_ctx("comptabilite"),
    )
    assert res.output["classe"] == 2


async def test_compte_799_max(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"numero_compte": 799}, make_ctx("comptabilite"),
    )
    assert res.output["classe"] == 7


# ============================================================================
# Ecritures - 6 tests
# ============================================================================

async def test_ecriture_equilibree(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"type": "ecriture", "total_debit": 1000, "total_credit": 1000},
        make_ctx("comptabilite"),
    )
    assert res.output["equilibre"] is True
    assert res.output["ecart"] == 0


async def test_ecriture_desequilibree_debit(registry) -> None:
    d = registry.get("comptabilite")
    val = await d.validate(
        {"type": "ecriture", "total_debit": 1100, "total_credit": 1000},
        make_ctx("comptabilite"),
    )
    assert val.valid is False


async def test_ecriture_desequilibree_credit(registry) -> None:
    d = registry.get("comptabilite")
    val = await d.validate(
        {"type": "ecriture", "total_debit": 900, "total_credit": 1000},
        make_ctx("comptabilite"),
    )
    assert val.valid is False


async def test_ecriture_achat_tva_deductible(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"type": "ecriture", "nature": "achat",
         "total_debit": 1190, "total_credit": 1190},
        make_ctx("comptabilite"),
    )
    assert res.output["compte_tva_deductible"] == 44566


async def test_ecriture_vente_tva_collectee(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"type": "ecriture", "nature": "vente",
         "total_debit": 1190, "total_credit": 1190},
        make_ctx("comptabilite"),
    )
    assert res.output["compte_tva_collectee"] == 44571


async def test_ecriture_grosse_somme(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"type": "ecriture", "total_debit": 1_000_000_000,
         "total_credit": 1_000_000_000},
        make_ctx("comptabilite"),
    )
    assert res.output["equilibre"] is True


# ============================================================================
# Metadata + schema - 6 tests
# ============================================================================

def test_comptabilite_domain_id() -> None:
    from app.domains.comptabilite import ComptabiliteDomain
    assert ComptabiliteDomain.domain_id == "comptabilite"


def test_comptabilite_supported_ops() -> None:
    from app.domains.comptabilite import ComptabiliteDomain
    assert "classer_compte" in ComptabiliteDomain.supported_operations
    assert "generer_bilan" in ComptabiliteDomain.supported_operations


def test_comptabilite_schema_numero_bounds() -> None:
    from app.domains.comptabilite import ComptabiliteDomain
    prop = ComptabiliteDomain.schema["properties"]["numero_compte"]
    assert prop["minimum"] == 100
    assert prop["maximum"] == 799


def test_comptabilite_type_enum() -> None:
    from app.domains.comptabilite import ComptabiliteDomain
    enum = ComptabiliteDomain.schema["properties"]["type"]["enum"]
    assert "ecriture" in enum and "bilan" in enum


async def test_comptabilite_rules_count(registry) -> None:
    from app.domains import RULES_ENGINE
    rules = RULES_ENGINE.get_rules("comptabilite")
    assert len(rules) >= 9


async def test_comptabilite_version() -> None:
    from app.domains.comptabilite import ComptabiliteDomain
    assert ComptabiliteDomain.version == "1.0.0"


# ============================================================================
# Integration - 4 tests
# ============================================================================

async def test_compta_process_via_router(registry) -> None:
    from app.core import DomainRouter
    r = DomainRouter(registry)
    res = await r.process(
        {"numero_compte": 411}, make_ctx("comptabilite"), "classer_compte",
    )
    assert res.success
    assert res.output["categorie"] == "tiers"


async def test_compta_report_json(registry) -> None:
    d = registry.get("comptabilite")
    rep = await d.report({"bilan_actif": 1000000, "bilan_passif": 1000000})
    assert rep.domain_id == "comptabilite"
    assert rep.content["bilan_actif"] == 1000000


async def test_compta_empty_input(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process({}, make_ctx("comptabilite"))
    assert res.success


async def test_compta_multiple_rules_applied(registry) -> None:
    d = registry.get("comptabilite")
    res = await d.process(
        {"type": "ecriture", "nature": "achat",
         "total_debit": 1190, "total_credit": 1190},
        make_ctx("comptabilite"),
    )
    assert len(res.rules_applied) >= 2
