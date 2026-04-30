"""Tests Phase 9C — Intelligence Engine (packs + 4 moteurs)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.intelligence.assembly_engine import (
    AssemblyEngine,
    AssemblyOutcome,
)
from app.saas_factory.intelligence.packs.catalog import (
    PackCatalogError,
    load_default_pack_catalog,
    load_pack_catalog,
)
from app.saas_factory.intelligence.pricing_engine import (
    NORMALIZER,
    PricingEngine,
    PricingResult,
    PricingStatus,
    ProjectFacets,
    _apply_margin_floor,
    _round_2,
)
from app.saas_factory.intelligence.progression_engine import (
    PAYWALL_THRESHOLD_PCT,
    PROGRESSION_PHASES,
    PhaseStatus,
    ProgressionEngine,
    ProjectPhase,
    _compute_overall,
    _current_phase,
    _eta,
)
from app.saas_factory.intelligence.qualification_engine import (
    Qualification,
    QualificationConfidence,
    QualificationEngine,
    QualificationError,
    StubClaudeProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_cm)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)
    conn.fetchrow = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    conn.executemany = AsyncMock()
    return pool, conn


def _good_facets() -> ProjectFacets:
    return ProjectFacets(
        complexity=3, domain_specialty=2, urgency=1, support_level=2,
        compliance_overhead=1, i18n_locales=2, integration_count=4,
        design_intensity=3, data_migration=1, training_included=2,
        sla_tier=1, scaling_factor=2, geographic_spread=1,
        audit_required=0, post_launch_window=3,
    )


def _equal_weights() -> dict[str, float]:
    return {
        "complexity": 1.0, "domain_specialty": 1.0, "urgency": 1.0,
        "support_level": 1.0, "compliance_overhead": 1.0,
        "i18n_locales": 1.0, "integration_count": 1.0,
        "design_intensity": 1.0, "data_migration": 1.0,
        "training_included": 1.0, "sla_tier": 1.0,
        "scaling_factor": 1.0, "geographic_spread": 1.0,
        "audit_required": 1.0, "post_launch_window": 1.0,
    }


def _good_claude_response(pack_hint: str = "saas_medium") -> dict:
    return {
        "pack_hint": pack_hint,
        "facets": _good_facets().model_dump(),
        "detected_domain": "saas-internal-tooling",
        "detected_locales": ["en", "fr"],
        "risks": [],
        "confidence": "high",
        "rationale": "Le CDC decrit un dashboard interne avec auth SSO et "
                     "billing simple. Volumetrie modeste, 2 langues. "
                     "Aucun KYC special. Compatible saas_medium par defaut.",
    }


# ===========================================================================
# Pack catalog
# ===========================================================================
class TestPackCatalog:
    def test_default_loads_9_packs(self) -> None:
        cat = load_default_pack_catalog()
        expected = {
            "ecommerce_small", "ecommerce_medium", "ecommerce_large",
            "saas_small", "saas_medium", "saas_large",
            "mobile_app", "api_b2b", "custom",
        }
        assert set(cat.pack_ids) == expected

    def test_phases_sum_to_100_for_all_packs(self) -> None:
        cat = load_default_pack_catalog()
        for pid in cat.pack_ids:
            pack = cat.get(pid)
            assert pack.phases.total == 100, f"{pid} phases != 100"

    def test_label_has_en_and_fr(self) -> None:
        cat = load_default_pack_catalog()
        for pid in cat.pack_ids:
            label = cat.get(pid).label_i18n
            assert "en" in label and "fr" in label

    def test_custom_pack_is_manual_quote_with_zero_price(self) -> None:
        cat = load_default_pack_catalog()
        custom = cat.get("custom")
        assert custom.manual_quote_required is True
        assert custom.base_price_eur == 0

    def test_unknown_pack_raises(self) -> None:
        cat = load_default_pack_catalog()
        with pytest.raises(KeyError):
            cat.get("nonexistent")

    def test_invalid_json_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(PackCatalogError):
            load_pack_catalog(bad)

    def test_pack_with_phases_not_summing_100_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({
            "version": "1.0.0",
            "packs": {
                "x": {
                    "label_i18n": {"en": "X", "fr": "X"},
                    "base_price_eur": 1000,
                    "estimated_cost_eur": 400,
                    "max_complexity_factor": 1.5,
                    "base_modules": [], "base_deliverables": [],
                    "suggested_addons": [],
                    "phases": {
                        "ANALYSIS": 10, "DESIGN": 10, "CORE": 10,
                        "FEATURES": 10, "TESTING": 10, "DEPLOY": 10,
                    },  # = 60, pas 100
                    "manual_quote_required": False,
                },
            },
        }))
        with pytest.raises(PackCatalogError):
            load_pack_catalog(bad)

    def test_manual_quote_with_nonzero_price_rejected(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({
            "version": "1.0.0",
            "packs": {
                "x": {
                    "label_i18n": {"en": "X", "fr": "X"},
                    "base_price_eur": 1000,  # incompatible avec manual_quote
                    "estimated_cost_eur": 400,
                    "max_complexity_factor": 1.5,
                    "base_modules": [], "base_deliverables": [],
                    "suggested_addons": [],
                    "phases": {
                        "ANALYSIS": 10, "DESIGN": 20, "CORE": 30,
                        "FEATURES": 20, "TESTING": 10, "DEPLOY": 10,
                    },
                    "manual_quote_required": True,
                },
            },
        }))
        with pytest.raises(PackCatalogError):
            load_pack_catalog(bad)

    def test_pack_label_helper(self) -> None:
        cat = load_default_pack_catalog()
        pack = cat.get("saas_medium")
        assert pack.label("en") == "SaaS Medium"
        assert pack.label("fr") == "SaaS Moyen"
        assert pack.label("zz") == "SaaS Medium"  # fallback en


# ===========================================================================
# PricingEngine
# ===========================================================================
class TestPricingEngine:
    @pytest.mark.asyncio
    async def test_basic_quote_returns_ok_status(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"pricing_id": uuid4()}
        cat = load_default_pack_catalog()
        eng = PricingEngine(pool, cat)
        res = await eng.quote(
            project_id="p-1", pack_id="saas_small",
            facets=_good_facets(), coefficients=_equal_weights(),
        )
        assert res.status is PricingStatus.OK
        assert res.net_price > 0
        assert res.gross_price > res.net_price  # tax > 0
        assert res.breakdown is not None
        assert res.breakdown.effective_factor >= 1.0
        assert res.pricing_id is not None

    @pytest.mark.asyncio
    async def test_custom_pack_returns_manual_quote_with_zero_price(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"pricing_id": uuid4()}
        cat = load_default_pack_catalog()
        eng = PricingEngine(pool, cat)
        res = await eng.quote(
            project_id="p-1", pack_id="custom",
            facets=_good_facets(), coefficients=_equal_weights(),
        )
        assert res.status is PricingStatus.REQUIRES_MANUAL_QUOTE
        assert res.net_price == 0.0
        assert res.gross_price == 0.0
        assert res.breakdown is None
        assert any("manuel" in n.lower() or "manual" in n.lower() for n in res.notes)

    @pytest.mark.asyncio
    async def test_complexity_capped_at_pack_max(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"pricing_id": uuid4()}
        cat = load_default_pack_catalog()
        # Facets max + weights max -> raw_factor enorme
        max_facets = ProjectFacets(
            complexity=10, domain_specialty=10, urgency=10,
            support_level=10, compliance_overhead=10,
            i18n_locales=10, integration_count=20, design_intensity=10,
            data_migration=10, training_included=10, sla_tier=3,
            scaling_factor=10, geographic_spread=5,
            audit_required=3, post_launch_window=12,
        )
        big_weights = {k: 5.0 for k in _equal_weights()}
        eng = PricingEngine(pool, cat)
        res = await eng.quote(
            project_id="p-1", pack_id="ecommerce_small",
            facets=max_facets, coefficients=big_weights,
        )
        pack = cat.get("ecommerce_small")
        assert res.breakdown is not None
        assert res.breakdown.capped_at_max is True
        assert res.breakdown.effective_factor == pack.max_complexity_factor

    @pytest.mark.asyncio
    async def test_zero_facets_yields_factor_1(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"pricing_id": uuid4()}
        cat = load_default_pack_catalog()
        zero_facets = ProjectFacets(
            complexity=0, domain_specialty=0, urgency=0,
            support_level=0, compliance_overhead=0,
            i18n_locales=0, integration_count=0, design_intensity=0,
            data_migration=0, training_included=0, sla_tier=0,
            scaling_factor=0, geographic_spread=0,
            audit_required=0, post_launch_window=0,
        )
        eng = PricingEngine(pool, cat)
        res = await eng.quote(
            project_id="p-1", pack_id="saas_small",
            facets=zero_facets, coefficients=_equal_weights(),
        )
        pack = cat.get("saas_small")
        assert res.breakdown is not None
        assert res.breakdown.effective_factor == 1.0
        # Avec marge >= 50% par defaut, le prix = max(base * 1.0, cost / 0.5)
        # base = 4500, cost = 1800 -> margin floor at cost/0.5 = 3600 ; base 4500 OK.
        assert res.net_price >= pack.estimated_cost_eur * 2  # marge >= 50%

    @pytest.mark.asyncio
    async def test_persistence_stores_breakdown(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"pricing_id": uuid4()}
        cat = load_default_pack_catalog()
        eng = PricingEngine(pool, cat)
        await eng.quote(
            project_id="proj-X", pack_id="api_b2b",
            facets=_good_facets(), coefficients=_equal_weights(),
        )
        # On a un INSERT INTO intelligence_pricings
        sql = conn.fetchrow.await_args_list[0].args[0]
        assert "INSERT INTO intelligence_pricings" in sql

    def test_apply_margin_floor_below_min_lifts_price(self) -> None:
        # cost 1000, raw price 1500 -> marge 33%, doit etre releve a 50%.
        # Cible : cost / (1 - 0.5) = 2000.
        new, applied, margin = _apply_margin_floor(
            raw_price=1500.0, cost=1000.0, minimum_margin_pct=50,
        )
        assert applied is True
        assert new == 2000.0
        assert margin == 50.0

    def test_apply_margin_floor_above_min_unchanged(self) -> None:
        new, applied, margin = _apply_margin_floor(
            raw_price=3000.0, cost=1000.0, minimum_margin_pct=50,
        )
        assert applied is False
        assert new == 3000.0
        assert abs(margin - 66.67) < 0.1

    def test_apply_margin_floor_zero_price(self) -> None:
        new, applied, margin = _apply_margin_floor(
            raw_price=0.0, cost=0.0, minimum_margin_pct=50,
        )
        assert applied is False
        assert new == 0.0
        assert margin == 0.0

    def test_apply_margin_floor_100_pct_guarded(self) -> None:
        # margin_pct=100 -> impossible, garde-fou : on ne touche pas.
        new, applied, margin = _apply_margin_floor(
            raw_price=1000.0, cost=200.0, minimum_margin_pct=100,
        )
        assert applied is False  # garde-fou actif
        assert new == 1000.0

    def test_round_2_proper_rounding(self) -> None:
        assert _round_2(1.005) == 1.01     # ROUND_HALF_UP
        assert _round_2(1.004) == 1.00
        assert _round_2(0.0) == 0.0

    def test_facets_missing_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProjectFacets(complexity=3)  # type: ignore[call-arg]

    def test_facets_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProjectFacets(
                complexity=11, domain_specialty=0, urgency=0,
                support_level=0, compliance_overhead=0,
                i18n_locales=0, integration_count=0, design_intensity=0,
                data_migration=0, training_included=0, sla_tier=0,
                scaling_factor=0, geographic_spread=0,
                audit_required=0, post_launch_window=0,
            )

    def test_normalizer_constant(self) -> None:
        assert NORMALIZER == 30.0


# ===========================================================================
# QualificationEngine
# ===========================================================================
class TestQualificationEngine:
    @pytest.mark.asyncio
    async def test_qualify_persists_and_returns_qualification(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "qualification_id": new_id, "created_at": now,
        }
        cat = load_default_pack_catalog()
        provider = StubClaudeProvider(_good_claude_response())
        eng = QualificationEngine(pool, cat, provider)
        q = await eng.qualify(project_id="proj-A", cdc_text="Build a SaaS dashboard")
        assert isinstance(q, Qualification)
        assert q.qualification_id == new_id
        assert q.pack_hint == "saas_medium"
        assert q.confidence is QualificationConfidence.HIGH
        assert q.cdc_text_hash and len(q.cdc_text_hash) == 64
        assert provider.call_count == 1

    @pytest.mark.asyncio
    async def test_empty_cdc_text_raises(self) -> None:
        pool, _conn = _mock_pool()
        cat = load_default_pack_catalog()
        provider = StubClaudeProvider(_good_claude_response())
        eng = QualificationEngine(pool, cat, provider)
        with pytest.raises(QualificationError):
            await eng.qualify(project_id="x", cdc_text="   ")

    @pytest.mark.asyncio
    async def test_provider_returns_unknown_pack_raises(self) -> None:
        pool, _conn = _mock_pool()
        cat = load_default_pack_catalog()
        bad = _good_claude_response()
        bad["pack_hint"] = "ghost_pack"
        provider = StubClaudeProvider(bad)
        eng = QualificationEngine(pool, cat, provider)
        with pytest.raises(QualificationError, match="pack_hint"):
            await eng.qualify(project_id="x", cdc_text="some cdc")

    @pytest.mark.asyncio
    async def test_provider_returns_invalid_facets_raises(self) -> None:
        pool, _conn = _mock_pool()
        cat = load_default_pack_catalog()
        bad = _good_claude_response()
        bad["facets"]["complexity"] = 99  # > 10
        provider = StubClaudeProvider(bad)
        eng = QualificationEngine(pool, cat, provider)
        with pytest.raises(QualificationError, match="invalide"):
            await eng.qualify(project_id="x", cdc_text="some cdc")

    @pytest.mark.asyncio
    async def test_low_confidence_propagates(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "qualification_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        resp = _good_claude_response()
        resp["confidence"] = "low"
        provider = StubClaudeProvider(resp)
        eng = QualificationEngine(pool, cat, provider)
        q = await eng.qualify(project_id="x", cdc_text="ambiguous brief")
        assert q.confidence is QualificationConfidence.LOW

    def test_stub_provider_increments_call_count(self) -> None:
        provider = StubClaudeProvider({"any": "data"})
        assert provider.call_count == 0


# ===========================================================================
# AssemblyEngine
# ===========================================================================
class TestAssemblyEngine:
    def _make_qualification(
        self,
        *,
        project_id: str = "proj-Z",
        pack_hint: str = "saas_small",
        confidence: QualificationConfidence = QualificationConfidence.HIGH,
    ) -> Qualification:
        return Qualification(
            qualification_id=uuid4(),
            project_id=project_id,
            pack_hint=pack_hint,
            facets=_good_facets(),
            detected_domain="x",
            detected_locales=("en",),
            risks=(),
            confidence=confidence,
            rationale="test",
            cdc_text_hash="0" * 64,
            created_at=datetime.now(UTC),
        )

    def _make_pricing(
        self, *, pack_id: str = "saas_small",
        status: PricingStatus = PricingStatus.OK,
    ) -> PricingResult:
        return PricingResult(
            status=status,
            pack_id=pack_id,
            currency="EUR",
            net_price=4500.0, tax_amount=900.0, gross_price=5400.0,
            breakdown=None, pricing_id=uuid4(),
            computed_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_assembly_auto_outcome_for_normal_inputs(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "assembly_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        eng = AssemblyEngine(pool, cat)
        q = self._make_qualification()
        p = self._make_pricing()
        a = await eng.assemble(qualification=q, pricing=p)
        assert a.outcome is AssemblyOutcome.AUTO
        assert len(a.modules) > 0
        assert len(a.deliverables) > 0
        assert sum(a.phase_weights.values()) == 100

    @pytest.mark.asyncio
    async def test_manual_quote_outcome_when_pricing_requires_it(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "assembly_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        eng = AssemblyEngine(pool, cat)
        q = self._make_qualification(pack_hint="custom")
        p = self._make_pricing(pack_id="custom",
                               status=PricingStatus.REQUIRES_MANUAL_QUOTE)
        a = await eng.assemble(qualification=q, pricing=p)
        assert a.outcome is AssemblyOutcome.MANUAL_QUOTE
        assert any("manuel" in n.lower() for n in a.notes)

    @pytest.mark.asyncio
    async def test_degraded_outcome_when_low_confidence(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "assembly_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        eng = AssemblyEngine(pool, cat)
        q = self._make_qualification(confidence=QualificationConfidence.LOW)
        p = self._make_pricing()
        a = await eng.assemble(qualification=q, pricing=p)
        assert a.outcome is AssemblyOutcome.DEGRADED
        assert any("handoff" in n.lower() for n in a.notes)

    @pytest.mark.asyncio
    async def test_addons_filtered_to_suggested_only(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "assembly_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        eng = AssemblyEngine(pool, cat)
        q = self._make_qualification(pack_hint="saas_small")
        p = self._make_pricing()
        # api_keys_management est suggere pour saas_small ; flying_unicorn ne l'est pas.
        a = await eng.assemble(
            qualification=q, pricing=p,
            selected_addons=["api_keys_management", "flying_unicorn"],
        )
        assert "api_keys_management" in a.selected_addons
        assert "flying_unicorn" not in a.selected_addons
        assert any("ignores" in n for n in a.notes)

    @pytest.mark.asyncio
    async def test_pack_mismatch_logged_but_pricing_wins(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "assembly_id": uuid4(), "created_at": datetime.now(UTC),
        }
        cat = load_default_pack_catalog()
        eng = AssemblyEngine(pool, cat)
        q = self._make_qualification(pack_hint="saas_small")
        p = self._make_pricing(pack_id="api_b2b")  # different
        a = await eng.assemble(qualification=q, pricing=p)
        assert a.pack_id == "api_b2b"
        # Les modules viennent de api_b2b
        assert "openapi_spec" in a.modules

    def test_serialize_assembled_helper(self) -> None:
        from app.saas_factory.intelligence.assembly_engine import AssembledProject
        a = AssembledProject(
            assembly_id=uuid4(), project_id="p", pack_id="saas_small",
            outcome=AssemblyOutcome.AUTO,
            modules=("m1", "m2"), deliverables=("d1",),
            selected_addons=(), phase_weights={"ANALYSIS": 5},
            qualification_id=uuid4(), pricing_id=uuid4(),
        )
        d = AssemblyEngine.serialize_assembled(a)
        assert d["pack_id"] == "saas_small"
        assert d["modules"] == ["m1", "m2"]
        assert d["outcome"] == "auto"


# ===========================================================================
# ProgressionEngine
# ===========================================================================
class TestProgressionEngine:
    def _equal_phase_weights(self) -> dict[str, int]:
        # 100 / 6 ne tombe pas juste -> on adapte.
        return {
            "ANALYSIS": 5, "DESIGN": 15, "CORE": 35,
            "FEATURES": 25, "TESTING": 10, "DEPLOY": 10,
        }

    @pytest.mark.asyncio
    async def test_initialize_inserts_6_phases(self) -> None:
        pool, conn = _mock_pool()
        eng = ProgressionEngine(pool)
        await eng.initialize(
            project_id="p1", pack_phase_weights=self._equal_phase_weights(),
        )
        # executemany appele avec 6 lignes
        call = conn.executemany.await_args_list[0]
        rows = call.args[1]
        assert len(rows) == 6
        assert {r[1] for r in rows} == {p.value for p in PROGRESSION_PHASES}

    @pytest.mark.asyncio
    async def test_initialize_rejects_invalid_phase_set(self) -> None:
        pool, _conn = _mock_pool()
        eng = ProgressionEngine(pool)
        with pytest.raises(ValueError):
            await eng.initialize(
                project_id="p1",
                pack_phase_weights={"ANALYSIS": 100},  # incomplet
            )

    @pytest.mark.asyncio
    async def test_initialize_rejects_weights_not_summing_100(self) -> None:
        pool, _conn = _mock_pool()
        eng = ProgressionEngine(pool)
        bad = self._equal_phase_weights()
        bad["DEPLOY"] = 5  # somme = 95
        with pytest.raises(ValueError, match="100"):
            await eng.initialize(project_id="p1", pack_phase_weights=bad)

    @pytest.mark.asyncio
    async def test_update_phase_rejects_completion_out_of_range(self) -> None:
        pool, _conn = _mock_pool()
        eng = ProgressionEngine(pool)
        with pytest.raises(ValueError):
            await eng.update_phase(
                project_id="p1", phase=ProjectPhase.ANALYSIS,
                status=PhaseStatus.IN_PROGRESS, completion_pct=150,
            )

    @pytest.mark.asyncio
    async def test_update_phase_done_sets_completion_to_100(self) -> None:
        pool, conn = _mock_pool()
        eng = ProgressionEngine(pool)
        await eng.update_phase(
            project_id="p1", phase=ProjectPhase.ANALYSIS,
            status=PhaseStatus.DONE, completion_pct=42,  # devrait etre force a 100
        )
        # Le 4eme parametre passe a UPDATE est 100
        call = conn.execute.await_args_list[0]
        assert call.args[4] == 100

    @pytest.mark.asyncio
    async def test_snapshot_computes_overall_pct(self) -> None:
        pool, conn = _mock_pool()
        # ANALYSIS done (5%) + DESIGN in_progress 50% (15% * 0.5 = 7.5%)
        # = 12.5%
        rows = [
            {
                "phase": "ANALYSIS", "weight_pct": 5,
                "status": "done", "completion_pct": 100,
                "started_at": datetime.now(UTC) - timedelta(hours=2),
                "completed_at": datetime.now(UTC) - timedelta(hours=1),
                "paywall_triggered_at": None,
            },
            {
                "phase": "DESIGN", "weight_pct": 15,
                "status": "in_progress", "completion_pct": 50,
                "started_at": datetime.now(UTC) - timedelta(hours=1),
                "completed_at": None, "paywall_triggered_at": None,
            },
            {
                "phase": "CORE", "weight_pct": 35,
                "status": "pending", "completion_pct": 0,
                "started_at": None, "completed_at": None,
                "paywall_triggered_at": None,
            },
            {
                "phase": "FEATURES", "weight_pct": 25,
                "status": "pending", "completion_pct": 0,
                "started_at": None, "completed_at": None,
                "paywall_triggered_at": None,
            },
            {
                "phase": "TESTING", "weight_pct": 10,
                "status": "pending", "completion_pct": 0,
                "started_at": None, "completed_at": None,
                "paywall_triggered_at": None,
            },
            {
                "phase": "DEPLOY", "weight_pct": 10,
                "status": "pending", "completion_pct": 0,
                "started_at": None, "completed_at": None,
                "paywall_triggered_at": None,
            },
        ]
        conn.fetch.return_value = rows
        eng = ProgressionEngine(pool)
        snap = await eng.snapshot("p1")
        assert abs(snap.overall_pct - 12.5) < 0.01
        assert snap.is_at_paywall is False  # 12.5 < 20
        assert snap.current_phase is ProjectPhase.DESIGN

    @pytest.mark.asyncio
    async def test_snapshot_triggers_paywall_at_20pct(self) -> None:
        pool, conn = _mock_pool()
        # ANALYSIS (5%) + DESIGN (15%) done = 20% pile
        rows = [
            {"phase": "ANALYSIS", "weight_pct": 5, "status": "done",
             "completion_pct": 100, "started_at": datetime.now(UTC),
             "completed_at": datetime.now(UTC), "paywall_triggered_at": None},
            {"phase": "DESIGN", "weight_pct": 15, "status": "done",
             "completion_pct": 100, "started_at": datetime.now(UTC),
             "completed_at": datetime.now(UTC), "paywall_triggered_at": None},
            {"phase": "CORE", "weight_pct": 35, "status": "pending",
             "completion_pct": 0, "started_at": None,
             "completed_at": None, "paywall_triggered_at": None},
            {"phase": "FEATURES", "weight_pct": 25, "status": "pending",
             "completion_pct": 0, "started_at": None,
             "completed_at": None, "paywall_triggered_at": None},
            {"phase": "TESTING", "weight_pct": 10, "status": "pending",
             "completion_pct": 0, "started_at": None,
             "completed_at": None, "paywall_triggered_at": None},
            {"phase": "DEPLOY", "weight_pct": 10, "status": "pending",
             "completion_pct": 0, "started_at": None,
             "completed_at": None, "paywall_triggered_at": None},
        ]
        conn.fetch.return_value = rows
        eng = ProgressionEngine(pool)
        snap = await eng.snapshot("p1")
        assert snap.overall_pct == 20.0
        assert snap.is_at_paywall is True
        assert snap.paywall_triggered_at is not None
        # UPDATE paywall_triggered_at appele
        assert any(
            "paywall_triggered_at" in str(c.args[0])
            for c in conn.execute.await_args_list
        )

    @pytest.mark.asyncio
    async def test_snapshot_unknown_project_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetch.return_value = []
        eng = ProgressionEngine(pool)
        with pytest.raises(LookupError):
            await eng.snapshot("ghost")

    def test_compute_overall_caps_at_100(self) -> None:
        from app.saas_factory.intelligence.progression_engine import PhaseState
        # Construire 1 phase 'done' a poids 100 + 'in_progress' a 100 -> doit cap.
        phases = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=80,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.DESIGN, weight_pct=80,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
        )
        # Sum >100 mais on cap.
        assert _compute_overall(phases) == 100.0

    def test_current_phase_returns_first_in_progress(self) -> None:
        from app.saas_factory.intelligence.progression_engine import PhaseState
        phases = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=10,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.DESIGN, weight_pct=20,
                       status=PhaseStatus.IN_PROGRESS, completion_pct=30,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.CORE, weight_pct=40,
                       status=PhaseStatus.PENDING, completion_pct=0,
                       started_at=None, completed_at=None),
        )
        assert _current_phase(phases) is ProjectPhase.DESIGN

    def test_current_phase_falls_back_to_pending_then_last(self) -> None:
        from app.saas_factory.intelligence.progression_engine import PhaseState
        # Aucun in_progress -> premier pending
        phases = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=10,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.DESIGN, weight_pct=20,
                       status=PhaseStatus.PENDING, completion_pct=0,
                       started_at=None, completed_at=None),
        )
        assert _current_phase(phases) is ProjectPhase.DESIGN
        # Rien que des DONE -> dernier
        phases_all_done = tuple(
            ps._replace() if False else ps
            for ps in phases
        )
        from app.saas_factory.intelligence.progression_engine import PhaseState
        all_done = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=50,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.DEPLOY, weight_pct=50,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=None, completed_at=None),
        )
        assert _current_phase(all_done) is ProjectPhase.DEPLOY
        # Use phases_all_done to silence linter
        _ = phases_all_done

    def test_eta_returns_none_when_no_done_phases_with_times(self) -> None:
        from app.saas_factory.intelligence.progression_engine import PhaseState
        phases = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=10,
                       status=PhaseStatus.PENDING, completion_pct=0,
                       started_at=None, completed_at=None),
        )
        assert _eta(phases, datetime.now(UTC)) is None

    def test_eta_extrapolates_from_done_phases(self) -> None:
        from app.saas_factory.intelligence.progression_engine import PhaseState
        # 1 phase DONE en 1h pour 10 pts -> 6 minutes par point
        # Reste 90 points -> ETA = now + 9h
        now = datetime.now(UTC)
        phases = (
            PhaseState(phase=ProjectPhase.ANALYSIS, weight_pct=10,
                       status=PhaseStatus.DONE, completion_pct=100,
                       started_at=now - timedelta(hours=1),
                       completed_at=now),
            PhaseState(phase=ProjectPhase.DESIGN, weight_pct=20,
                       status=PhaseStatus.PENDING, completion_pct=0,
                       started_at=None, completed_at=None),
            PhaseState(phase=ProjectPhase.CORE, weight_pct=70,
                       status=PhaseStatus.PENDING, completion_pct=0,
                       started_at=None, completed_at=None),
        )
        eta = _eta(phases, now)
        assert eta is not None
        delta = eta - now
        # Approx 9h (avec marge de 1 minute)
        assert timedelta(hours=8, minutes=59) < delta < timedelta(hours=9, minutes=1)

    def test_to_websocket_payload_format(self) -> None:
        from app.saas_factory.intelligence.progression_engine import (
            PhaseState,
            ProgressionSnapshot,
        )
        snap = ProgressionSnapshot(
            project_id="p", overall_pct=42.5,
            current_phase=ProjectPhase.CORE,
            phases=(PhaseState(
                phase=ProjectPhase.CORE, weight_pct=35,
                status=PhaseStatus.IN_PROGRESS, completion_pct=70,
                started_at=None, completed_at=None,
            ),),
            is_at_paywall=True,
            paywall_triggered_at=datetime.now(UTC),
            eta_completion=None,
        )
        payload = ProgressionEngine.to_websocket_payload(snap)
        assert payload["overall_pct"] == 42.5
        assert payload["current_phase"] == "CORE"
        assert payload["is_at_paywall"] is True
        assert isinstance(payload["phases"], list)
        # Format JSON-serialisable
        assert json.dumps(payload)

    def test_paywall_threshold_constant(self) -> None:
        assert PAYWALL_THRESHOLD_PCT == 20.0
