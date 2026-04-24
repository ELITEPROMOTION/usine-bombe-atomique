"""Tests domaine logistique (30 tests)."""
from __future__ import annotations

import pytest

from .conftest import make_ctx

pytestmark = pytest.mark.asyncio


# ============================================================================
# Stock reappro - 8 tests
# ============================================================================

async def test_stock_sous_seuil_reappro(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 50, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output["besoin_reappro"] is True
    assert res.output["quantite_commandee"] == 450


async def test_stock_above_seuil_no_reappro(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 200, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output.get("besoin_reappro") is not True


async def test_stock_critique_urgence(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 15, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output["urgence"] is True


async def test_stock_boundary_exact(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 100, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    # <= declenche
    assert res.output["besoin_reappro"] is True


async def test_stock_surstockage(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 800, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output.get("surstockage") is True


async def test_stock_zero(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 0, "seuil_min": 10, "seuil_max": 100,
         "seuil_critique": 5},
        make_ctx("logistique"),
    )
    assert res.output["besoin_reappro"] is True
    assert res.output["urgence"] is True


async def test_stock_plein(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 500, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output.get("besoin_reappro") is not True
    assert res.output.get("surstockage") is not True


async def test_stock_just_above_surstockage(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"stock_actuel": 751, "seuil_min": 100, "seuil_max": 500,
         "seuil_critique": 20},
        make_ctx("logistique"),
    )
    assert res.output.get("surstockage") is True


# ============================================================================
# Valorisation CMP - 3 tests
# ============================================================================

async def test_cmp_calcul(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"methode": "cmp", "stock_actuel": 100, "prix_unitaire": 10,
         "nouveaux_arrivages": 50, "nouveau_prix": 20,
         "seuil_min": 0, "seuil_max": 1000, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    # (100*10 + 50*20) / (100+50) = 2000/150 = 13.33
    assert abs(res.output["cmp"] - 13.333333) < 0.001


async def test_cmp_stock_vide(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"methode": "cmp", "stock_actuel": 0, "prix_unitaire": 0,
         "nouveaux_arrivages": 100, "nouveau_prix": 15,
         "seuil_min": 0, "seuil_max": 1000, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    assert res.output["cmp"] == 15


async def test_cmp_non_methode_ignore(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"methode": "fifo", "stock_actuel": 100, "prix_unitaire": 10,
         "seuil_min": 0, "seuil_max": 1000, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    assert "cmp" not in res.output


# ============================================================================
# Peremption - 3 tests
# ============================================================================

async def test_peremption_30j_alerte(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"jours_avant_peremption": 20, "stock_actuel": 10, "seuil_min": 0,
         "seuil_max": 100, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    assert res.output["alerte_peremption"] is True


async def test_peremption_7j_urgence(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"jours_avant_peremption": 5, "stock_actuel": 10, "seuil_min": 0,
         "seuil_max": 100, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    assert res.output["urgence"] is True


async def test_peremption_60j_no_alerte(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"jours_avant_peremption": 60, "stock_actuel": 10, "seuil_min": 0,
         "seuil_max": 100, "seuil_critique": 0},
        make_ctx("logistique"),
    )
    assert res.output.get("alerte_peremption") is not True


# ============================================================================
# Import/export DZ - 8 tests
# ============================================================================

async def test_import_standard_30pct(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "import", "categorie": "standard", "valeur_caf": 100_000},
        make_ctx("logistique"),
    )
    assert res.output["droits_douane_taux"] == 0.30
    assert res.output["droits_douane_montant"] == 30_000


async def test_import_matiere_premiere_5pct(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "import", "categorie": "matiere_premiere",
         "valeur_caf": 100_000},
        make_ctx("logistique"),
    )
    assert res.output["droits_douane_taux"] == 0.05
    assert res.output["droits_douane_montant"] == 5_000


async def test_export_exonere(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "export", "valeur_caf": 100_000},
        make_ctx("logistique"),
    )
    assert res.output["droits_douane_taux"] == 0.0
    assert res.output["exoneration"] is True


async def test_import_zero_valeur(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "import", "categorie": "standard", "valeur_caf": 0},
        make_ctx("logistique"),
    )
    assert res.output["droits_douane_montant"] == 0


async def test_import_valeur_elevee(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "import", "categorie": "standard",
          "valeur_caf": 1_000_000_000},
        make_ctx("logistique"),
    )
    assert res.output["droits_douane_montant"] == 300_000_000


async def test_transfert_operation_no_duty(registry) -> None:
    d = registry.get("logistique")
    res = await d.process(
        {"operation": "transfert", "valeur_caf": 100_000},
        make_ctx("logistique"),
    )
    assert "droits_douane_taux" not in res.output


async def test_export_vs_import_same_value(registry) -> None:
    d = registry.get("logistique")
    r_imp = await d.process(
        {"operation": "import", "categorie": "standard", "valeur_caf": 100},
        make_ctx("logistique"),
    )
    r_exp = await d.process(
        {"operation": "export", "valeur_caf": 100},
        make_ctx("logistique"),
    )
    assert r_imp.output["droits_douane_montant"] > r_exp.output["droits_douane_montant"]


async def test_metadata_logistique() -> None:
    from app.domains.logistique import LogistiqueDomain
    assert LogistiqueDomain.domain_id == "logistique"
    assert len(LogistiqueDomain.supported_operations) >= 4


# ============================================================================
# Engine + edge - 8 tests
# ============================================================================

async def test_logistique_rules_loaded(registry) -> None:
    from app.domains import RULES_ENGINE
    rules = RULES_ENGINE.get_rules("logistique")
    assert len(rules) >= 6


async def test_valid_schema_operation_enum() -> None:
    from app.domains.logistique import LogistiqueDomain
    enum = LogistiqueDomain.schema["properties"]["operation"]["enum"]
    assert "import" in enum and "export" in enum


async def test_logistique_empty_input(registry) -> None:
    d = registry.get("logistique")
    res = await d.process({}, make_ctx("logistique"))
    assert res.success
    assert len(res.rules_applied) == 0


async def test_logistique_missing_seuils_partial(registry) -> None:
    d = registry.get("logistique")
    # Pas crash meme si champs manquent
    res = await d.process({"stock_actuel": 10}, make_ctx("logistique"))
    # Regle stock fait reference a seuil_min absent -> pas de match (expr echoue)
    assert res.success


async def test_logistique_ctx_tenant_propage(registry) -> None:
    d = registry.get("logistique")
    ctx = make_ctx("logistique", tenant_id="dendani-logistique")
    assert ctx.tenant_id == "dendani-logistique"
    res = await d.process({"operation": "export", "valeur_caf": 10}, ctx)
    assert res.correlation_id == ctx.correlation_id


async def test_logistique_locale_default() -> None:
    ctx = make_ctx("logistique")
    assert ctx.locale == "fr-DZ"


async def test_logistique_timezone_alger() -> None:
    ctx = make_ctx("logistique")
    assert ctx.timezone_name == "Africa/Algiers"


async def test_logistique_report_json(registry) -> None:
    d = registry.get("logistique")
    rep = await d.report({"summary": "ok"})
    assert rep.format == "json"
