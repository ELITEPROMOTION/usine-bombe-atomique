"""Tests domaine rh (30 tests)."""
from __future__ import annotations

import pytest

from .conftest import make_ctx

pytestmark = pytest.mark.asyncio


# ============================================================================
# CNAS - 5 tests
# ============================================================================

async def test_cnas_salarie_9pct(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 100_000}, make_ctx("rh"),
    )
    assert res.output["cnas_salarie_taux"] == 0.09
    assert res.output["cnas_salarie_montant"] == 9_000


async def test_cnas_employeur_26pct(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 100_000}, make_ctx("rh"),
    )
    assert res.output["cnas_employeur_taux"] == 0.26
    assert res.output["cnas_employeur_montant"] == 26_000


async def test_cnas_zero_salaire(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 0}, make_ctx("rh"),
    )
    assert res.output.get("cnas_salarie_montant", 0) == 0


async def test_cnas_salaire_eleve(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 500_000}, make_ctx("rh"),
    )
    assert res.output["cnas_salarie_montant"] == 45_000
    assert res.output["cnas_employeur_montant"] == 130_000


async def test_cnas_total_cout_employeur(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 100_000}, make_ctx("rh"),
    )
    total = res.output["cnas_salarie_montant"] + res.output["cnas_employeur_montant"]
    assert total == 35_000


# ============================================================================
# IRG mensuel - 3 tests
# ============================================================================

async def test_irg_mensuel_tr1_exonere(registry) -> None:
    d = registry.get("rh")
    # 10 989 * 0.91 = 10 000 net (tranche 1)
    res = await d.process(
        {"salaire_brut_mensuel": 10_989}, make_ctx("rh"),
    )
    assert res.output.get("irg_mensuel", 0) == 0


async def test_irg_mensuel_net_calcule(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 10_989}, make_ctx("rh"),
    )
    expected_net = 10_989 - 10_989 * 0.09
    assert abs(res.output["salaire_net"] - expected_net) < 0.01


async def test_irg_mensuel_au_dessus_tranche1(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 50_000}, make_ctx("rh"),
    )
    # Salaire net apres CNAS = 45500 > 10000 : regle tr1 ne match pas
    assert "irg_mensuel" not in res.output or res.output.get("irg_mensuel") != 0


# ============================================================================
# SMIG - 3 tests
# ============================================================================

async def test_smig_alerte_sous_20000(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 15_000}, make_ctx("rh"),
    )
    assert res.output.get("alerte_sous_smig") is True
    assert res.output["manque"] == 5000


async def test_smig_20000_ok(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 20_000}, make_ctx("rh"),
    )
    assert res.output.get("alerte_sous_smig") is not True


async def test_smig_valeur_2026(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 10_000}, make_ctx("rh"),
    )
    assert res.output["smig_dz"] == 20000


# ============================================================================
# Conges - 8 tests
# ============================================================================

async def test_conges_annuels_2_5j_par_mois(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"mois_travailles": 12}, make_ctx("rh"),
    )
    assert res.output["conges_acquis_jours"] == 30.0


async def test_conges_6_mois(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"mois_travailles": 6}, make_ctx("rh"),
    )
    assert res.output["conges_acquis_jours"] == 15.0


async def test_conges_max_30j(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"mois_travailles": 24}, make_ctx("rh"),
    )
    assert res.output["conges_max_annuel"] == 30


async def test_maternite_98_jours(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"type_conge": "maternite"}, make_ctx("rh"),
    )
    assert res.output["duree_jours"] == 98
    assert res.output["taux_remuneration"] == 1.0
    assert res.output["finance_par"] == "cnas"


async def test_maternite_rate_100pct(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"type_conge": "maternite"}, make_ctx("rh"),
    )
    assert res.output["taux_remuneration"] == 1.0


async def test_maladie_taux_50_100(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"type_conge": "maladie"}, make_ctx("rh"),
    )
    assert res.output["taux_15_premiers"] == 0.50
    assert res.output["taux_au_dela"] == 1.0
    assert res.output["jours_employeur"] == 15


async def test_conge_annuel_type_ignore_maternite_rules(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"type_conge": "annuel", "mois_travailles": 12}, make_ctx("rh"),
    )
    assert "duree_jours" not in res.output


async def test_conges_zero_mois(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"mois_travailles": 0}, make_ctx("rh"),
    )
    # La regle ne declenche pas (>= 1)
    assert "conges_acquis_jours" not in res.output


# ============================================================================
# Metadata + integration - 6 tests
# ============================================================================

def test_rh_domain_id() -> None:
    from app.domains.rh import RHDomain
    assert RHDomain.domain_id == "rh"


def test_rh_supported_operations() -> None:
    from app.domains.rh import RHDomain
    assert "calculer_paie" in RHDomain.supported_operations
    assert "calculer_conges" in RHDomain.supported_operations


def test_rh_schema_statut_enum() -> None:
    from app.domains.rh import RHDomain
    enum = RHDomain.schema["properties"]["statut"]["enum"]
    assert set(enum) == {"cdi", "cdd", "stagiaire", "apprenti"}


def test_rh_schema_type_conge_enum() -> None:
    from app.domains.rh import RHDomain
    enum = RHDomain.schema["properties"]["type_conge"]["enum"]
    assert "maternite" in enum


async def test_rh_rules_count(registry) -> None:
    from app.domains import RULES_ENGINE
    rules = RULES_ENGINE.get_rules("rh")
    assert len(rules) >= 7


async def test_rh_version_2026(registry) -> None:
    d = registry.get("rh")
    assert "2026" in d.version


# ============================================================================
# Edge cases - 5 tests
# ============================================================================

async def test_rh_empty_input(registry) -> None:
    d = registry.get("rh")
    res = await d.process({}, make_ctx("rh"))
    assert res.success


async def test_rh_both_paie_et_conge(registry) -> None:
    d = registry.get("rh")
    res = await d.process(
        {"salaire_brut_mensuel": 100_000, "mois_travailles": 12,
         "type_conge": "maternite"},
        make_ctx("rh"),
    )
    # Plusieurs regles se declenchent en meme temps
    assert len(res.rules_applied) >= 3


async def test_rh_permissions_wildcard(registry) -> None:
    from app.core import DomainContext, DomainRouter
    ctx = DomainContext(
        tenant_id="x", user_id="y", domain_id="rh",
        permissions=frozenset(["rh:*"]),
    )
    r = DomainRouter(registry)
    res = await r.process({"salaire_brut_mensuel": 50_000}, ctx, "calculer_paie")
    assert res.success


async def test_rh_process_via_router(registry) -> None:
    from app.core import DomainRouter
    r = DomainRouter(registry)
    res = await r.process(
        {"salaire_brut_mensuel": 80_000}, make_ctx("rh"), "calculer_paie",
    )
    assert res.success


async def test_rh_salaire_negatif_ignore(registry) -> None:
    d = registry.get("rh")
    res = await d.process({"salaire_brut_mensuel": -1000}, make_ctx("rh"))
    # Aucune regle ne match (condition > 0)
    assert res.success
    assert res.output.get("cnas_salarie_montant") is None
