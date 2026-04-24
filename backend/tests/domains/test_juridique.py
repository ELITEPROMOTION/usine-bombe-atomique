"""Tests domaine juridique (30 tests)."""
from __future__ import annotations

import pytest

from .conftest import make_ctx

pytestmark = pytest.mark.asyncio


# ============================================================================
# Contrats vente - 10 tests
# ============================================================================

async def test_vente_immo_droits_5pct(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 10_000_000,
         "vendeur": "Alice", "acheteur": "Bob"},
        make_ctx("juridique"),
    )
    assert res.success
    assert res.output["droits_enregistrement_taux"] == 0.05
    assert res.output["droits_enregistrement_montant"] == 500_000


async def test_vente_immo_timbre_1000(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 5_000_000,
         "vendeur": "Alice", "acheteur": "Bob"},
        make_ctx("juridique"),
    )
    assert res.output["droit_timbre_montant"] == 1000


async def test_vente_mobiliere_2pct(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "mobilier", "prix": 100_000,
         "vendeur": "Alice", "acheteur": "Bob"},
        make_ctx("juridique"),
    )
    assert res.output["droits_enregistrement_taux"] == 0.02
    assert res.output["droits_enregistrement_montant"] == 2_000


async def test_vente_parties_manquantes_rejete(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 1000,
         "vendeur": None, "acheteur": "Bob"},
        make_ctx("juridique"),
    )
    # Guard empeche le calcul
    assert res.success is False or "parties_ok" not in res.output


async def test_vente_vendeur_complexe_object(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 5_000_000,
         "vendeur": {"name": "Entreprise X", "nif": "12345"},
         "acheteur": {"name": "Entreprise Y", "nif": "67890"}},
        make_ctx("juridique"),
    )
    assert res.success


async def test_vente_immo_droits_cumul_timbre(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 2_000_000,
         "vendeur": "X", "acheteur": "Y"},
        make_ctx("juridique"),
    )
    assert "droits_enregistrement_montant" in res.output
    assert "droit_timbre_montant" in res.output


async def test_vente_prix_zero(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 0,
         "vendeur": "X", "acheteur": "Y"},
        make_ctx("juridique"),
    )
    assert res.output["droits_enregistrement_montant"] == 0


async def test_vente_prix_tres_eleve(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 1_000_000_000,
         "vendeur": "X", "acheteur": "Y"},
        make_ctx("juridique"),
    )
    assert res.output["droits_enregistrement_montant"] == 50_000_000


async def test_contrat_vente_applied_rule_ids(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "vente", "categorie": "immobilier", "prix": 1000,
         "vendeur": "X", "acheteur": "Y"},
        make_ctx("juridique"),
    )
    assert any("vente_immo" in rid for rid in res.rules_applied)


async def test_vente_non_ventetype_ignore(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "donation", "categorie": "immobilier", "prix": 100},
        make_ctx("juridique"),
    )
    # Aucune regle vente_* ne match
    vente_rules = [r for r in res.rules_applied if "vente" in r]
    assert len(vente_rules) == 0


# ============================================================================
# Baux commerciaux - 8 tests
# ============================================================================

async def test_bail_commercial_duree_24_ok(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 24,
         "loyer_mensuel": 50_000, "caution": 100_000},
        make_ctx("juridique"),
    )
    assert res.success
    assert res.output["conformite_duree"] is True


async def test_bail_commercial_duree_lt_24_nonconforme(registry) -> None:
    d = registry.get("juridique")
    val = await d.validate(
        {"type_acte": "bail_commercial", "duree_mois": 12,
         "loyer_mensuel": 50_000},
        make_ctx("juridique"),
    )
    assert val.valid is False


async def test_bail_commercial_caution_ok_3_mois(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 36,
         "loyer_mensuel": 100_000, "caution": 300_000},
        make_ctx("juridique"),
    )
    assert res.output["caution_valide"] is True


async def test_bail_caution_excede(registry) -> None:
    d = registry.get("juridique")
    val = await d.validate(
        {"type_acte": "bail_commercial", "duree_mois": 36,
         "loyer_mensuel": 100_000, "caution": 500_000},
        make_ctx("juridique"),
    )
    assert val.valid is False


async def test_bail_revision_5pct_ok(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 36,
         "loyer_mensuel": 100_000, "revision_annuelle": 0.04},
        make_ctx("juridique"),
    )
    assert res.output["revision_valide"] is True


async def test_bail_revision_above_5pct(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 36,
         "loyer_mensuel": 100_000, "revision_annuelle": 0.08},
        make_ctx("juridique"),
    )
    assert res.output.get("revision_valide") is False


async def test_bail_caution_max_computed(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 36,
         "loyer_mensuel": 75_000, "caution": 100_000},
        make_ctx("juridique"),
    )
    assert res.output["caution_max"] == 75_000 * 3


async def test_bail_duree_5ans(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 60,
         "loyer_mensuel": 50_000},
        make_ctx("juridique"),
    )
    assert res.output["conformite_duree"] is True


# ============================================================================
# Metadata + schema - 6 tests
# ============================================================================

def test_juridique_domain_id() -> None:
    from app.domains.juridique import JuridiqueDomain
    assert JuridiqueDomain.domain_id == "juridique"


def test_juridique_schema_type_acte_required() -> None:
    from app.domains.juridique import JuridiqueDomain
    assert "type_acte" in JuridiqueDomain.schema["required"]


def test_juridique_schema_enum_type_acte() -> None:
    from app.domains.juridique import JuridiqueDomain
    enum = JuridiqueDomain.schema["properties"]["type_acte"]["enum"]
    assert "vente" in enum
    assert "bail_commercial" in enum


async def test_juridique_missing_type_acte_invalid(registry) -> None:
    d = registry.get("juridique")
    val = await d.validate({"prix": 1000}, make_ctx("juridique"))
    assert val.valid is False
    assert any("MISSING_FIELD" in i.code for i in val.issues)


async def test_juridique_rules_count(registry) -> None:
    from app.domains import RULES_ENGINE
    rules = RULES_ENGINE.get_rules("juridique")
    assert len(rules) >= 6


async def test_juridique_supported_operations(registry) -> None:
    d = registry.get("juridique")
    assert "valider_contrat" in d.supported_operations
    assert "calculer_droits" in d.supported_operations


# ============================================================================
# Due diligence / edge cases - 6 tests
# ============================================================================

async def test_acte_inconnu_ignore(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "contrat_travail"},
        make_ctx("juridique"),
    )
    # Aucune regle specifique, success quand meme
    assert res.success


async def test_empty_input_validation(registry) -> None:
    d = registry.get("juridique")
    val = await d.validate({}, make_ctx("juridique"))
    assert val.valid is False


async def test_ctx_has_juridique_permission(registry) -> None:
    ctx = make_ctx("juridique")
    assert ctx.has_permission("juridique:process")
    assert ctx.has_permission("juridique:any_op")


async def test_ctx_correlation_id_unique(registry) -> None:
    ctx1 = make_ctx("juridique")
    ctx2 = make_ctx("juridique")
    assert ctx1.correlation_id != ctx2.correlation_id


async def test_bail_all_fields_enriched(registry) -> None:
    d = registry.get("juridique")
    res = await d.process(
        {"type_acte": "bail_commercial", "duree_mois": 48,
         "loyer_mensuel": 80_000, "caution": 240_000, "revision_annuelle": 0.03},
        make_ctx("juridique"),
    )
    assert "conformite_duree" in res.output
    assert "caution_valide" in res.output
    assert "revision_valide" in res.output


async def test_report_generated(registry) -> None:
    d = registry.get("juridique")
    rep = await d.report({"foo": "bar"}, format="json")
    assert rep.domain_id == "juridique"
    assert rep.format == "json"
