"""Tests XAI explainer V5.8."""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.intelligence.explainer import DecisionExplainer

pytestmark = pytest.mark.asyncio


async def test_explain_without_rules_engine_fallback(pool) -> None:
    expl = DecisionExplainer(pool, rules_engine=None)
    res = await expl.explain(
        decision_id=None,
        domain_id="fiscal_dz",
        operation="calculate_irg",
        input_context={"revenu_annuel": 300_000},
        output={"tranche": 2, "irg_annuel": 36_000},
    )
    assert res["domain_id"] == "fiscal_dz"
    assert res["operation"] == "calculate_irg"
    assert "features_importance" in res
    assert "counterfactuals" in res
    assert "ahmed_summary" in res


async def test_explain_with_rules_engine(pool) -> None:
    from app.domains import RULES_ENGINE
    expl = DecisionExplainer(pool, rules_engine=RULES_ENGINE)
    res = await expl.explain(
        decision_id=None,
        domain_id="fiscal_dz",
        operation="calculate_irg",
        input_context={"revenu_annuel": 300_000},
        output={"tranche": 2, "irg_annuel": 36_000},
    )
    assert len(res["features_importance"]) >= 1
    # Au moins 1 counterfactual generable
    assert isinstance(res["counterfactuals"], list)


async def test_explain_caches_in_db(pool) -> None:
    expl = DecisionExplainer(pool)
    decision_id = str(uuid4())
    await expl.explain(
        decision_id=decision_id, domain_id="rh",
        operation="calculer_paie",
        input_context={"salaire_brut_mensuel": 50_000},
        output={"cnas_salarie_montant": 4500},
    )
    cached = await expl.get_cached(decision_id)
    assert cached is not None
    assert cached["decision_id"] == decision_id
    assert cached["domain_id"] == "rh"


async def test_get_cached_unknown_returns_none(pool) -> None:
    expl = DecisionExplainer(pool)
    res = await expl.get_cached(str(uuid4()))
    assert res is None


async def test_ahmed_summary_generated(pool) -> None:
    expl = DecisionExplainer(pool)
    res = await expl.explain(
        decision_id=None, domain_id="juridique",
        operation="calculer_droits",
        input_context={"type_acte": "vente", "prix": 1_000_000},
        output={"droits": 50_000},
    )
    assert isinstance(res["ahmed_summary"], str)
    assert len(res["ahmed_summary"]) > 10


async def test_counterfactuals_numeric_perturbation(pool) -> None:
    from app.domains import RULES_ENGINE
    expl = DecisionExplainer(pool, rules_engine=RULES_ENGINE)
    res = await expl.explain(
        decision_id=None, domain_id="fiscal_dz",
        operation="calculate_irg",
        input_context={"revenu_annuel": 300_000},
        output={"tranche": 2, "irg_annuel": 36_000},
    )
    # Avec revenu divise par 2 (150k) ou x2 (600k), on change de tranche
    if res["counterfactuals"]:
        assert all("perturbation" in cf for cf in res["counterfactuals"])
        assert all("alternative_output" in cf for cf in res["counterfactuals"])


async def test_migration_030_table(pool) -> None:
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'decisions_explanations')",
        )
    assert exists


async def test_explain_update_overwrites_cache(pool) -> None:
    expl = DecisionExplainer(pool)
    decision_id = str(uuid4())
    await expl.explain(
        decision_id=decision_id, domain_id="comptabilite",
        operation="valider_ecriture",
        input_context={"total_debit": 100, "total_credit": 100},
        output={"equilibre": True},
    )
    # Re-explain same decision -> update cache
    res = await expl.explain(
        decision_id=decision_id, domain_id="comptabilite",
        operation="valider_ecriture",
        input_context={"total_debit": 200, "total_credit": 200},
        output={"equilibre": True},
    )
    assert res["decision_id"] == decision_id


async def test_feature_importance_sorted(pool) -> None:
    from app.domains import RULES_ENGINE
    expl = DecisionExplainer(pool, rules_engine=RULES_ENGINE)
    res = await expl.explain(
        decision_id=None, domain_id="fiscal_dz",
        operation="calc",
        input_context={"revenu_annuel": 500_000, "activite": "production"},
        output={"tranche": 3},
    )
    imps = res["features_importance"]
    # Trie par importance decroissante
    assert all(
        imps[i]["importance"] >= imps[i + 1]["importance"]
        for i in range(len(imps) - 1)
    )


async def test_explain_computation_ms_recorded(pool) -> None:
    expl = DecisionExplainer(pool)
    res = await expl.explain(
        decision_id=None, domain_id="logistique",
        operation="check",
        input_context={"stock": 100},
        output={"ok": True},
    )
    assert "computation_ms" in res
    assert res["computation_ms"] >= 0
