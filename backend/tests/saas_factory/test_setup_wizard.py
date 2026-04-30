"""Tests Phase 9B — Setup Wizard Ahmed (4 etapes)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.setup_wizard.defaults import (
    default_brand_identity,
    default_operations,
    default_pricing_baseline,
    default_service_catalog,
)
from app.saas_factory.setup_wizard.steps import (
    ALL_PACKS,
    COEFFICIENT_KEYS,
    WIZARD_STEP_ORDER,
    BrandIdentityStep,
    OperationsDefaultsStep,
    PricingBaselineStep,
    PricingCoefficient,
    ServiceCatalogStep,
    StepKey,
)
from app.saas_factory.setup_wizard.wizard_engine import (
    PlatformConfig,
    WizardEngine,
    WizardNotReadyError,
    WizardState,
    WizardStatus,
    _next_step,
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
    return pool, conn


# ===========================================================================
# Step 1 — Brand & Identity
# ===========================================================================
class TestBrandIdentityStep:
    def test_default_loads(self) -> None:
        b = default_brand_identity()
        assert b.platform_name == "UBA Studio Platform"
        assert b.default_currency == "EUR"

    def test_invalid_logo_url_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrandIdentityStep(
                platform_name="X",
                logo_url="ftp://nope",  # http(s) only
                primary_color="#000000",
                support_email="a@b.com",
                default_locale="en",
                default_timezone="UTC",
                default_currency="EUR",
            )

    def test_invalid_color_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrandIdentityStep(
                platform_name="X", logo_url="https://x.com",
                primary_color="not-a-color",
                support_email="a@b.com", default_locale="en",
                default_timezone="UTC", default_currency="EUR",
            )

    def test_unsupported_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrandIdentityStep(
                platform_name="X", logo_url="https://x.com",
                primary_color="#000000", support_email="a@b.com",
                default_locale="en", default_timezone="UTC",
                default_currency="XBT",  # type: ignore[arg-type]
            )

    def test_short_platform_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrandIdentityStep(
                platform_name="X",  # 1 char < min 2
                logo_url="https://x.com", primary_color="#000000",
                support_email="a@b.com", default_locale="en",
                default_timezone="UTC", default_currency="EUR",
            )


# ===========================================================================
# Step 2 — Pricing Baseline
# ===========================================================================
class TestPricingBaselineStep:
    def test_default_has_15_coefficients(self) -> None:
        p = default_pricing_baseline()
        assert len(p.coefficients) == 15
        assert {c.key for c in p.coefficients} == set(COEFFICIENT_KEYS)
        assert p.minimum_margin_pct >= 50

    def test_minimum_margin_below_50_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingBaselineStep(
                base_currency="EUR", minimum_margin_pct=49,
                default_vat_pct=20.0,
                coefficients=[PricingCoefficient(key=k, weight=1.0)
                              for k in COEFFICIENT_KEYS],
            )

    def test_less_than_15_coefficients_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingBaselineStep(
                base_currency="EUR", minimum_margin_pct=55,
                default_vat_pct=20.0,
                coefficients=[PricingCoefficient(key=k, weight=1.0)
                              for k in COEFFICIENT_KEYS[:14]],
            )

    def test_unknown_coefficient_key_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingCoefficient(key="not_a_known_key", weight=1.0)

    def test_duplicate_coefficient_key_rejected(self) -> None:
        coeffs = [PricingCoefficient(key=k, weight=1.0) for k in COEFFICIENT_KEYS]
        # Remplace le dernier par un doublon
        coeffs[-1] = PricingCoefficient(key=COEFFICIENT_KEYS[0], weight=2.0)
        with pytest.raises(ValidationError):
            PricingBaselineStep(
                base_currency="EUR", minimum_margin_pct=55,
                default_vat_pct=20.0, coefficients=coeffs,
            )

    def test_bounds_inverted_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingCoefficient(
                key=COEFFICIENT_KEYS[0], weight=1.0,
                bounded_min=2.0, bounded_max=1.0,
            )

    def test_vat_above_30_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PricingBaselineStep(
                base_currency="EUR", minimum_margin_pct=55,
                default_vat_pct=31.0,
                coefficients=[PricingCoefficient(key=k, weight=1.0)
                              for k in COEFFICIENT_KEYS],
            )


# ===========================================================================
# Step 3 — Service Catalog
# ===========================================================================
class TestServiceCatalogStep:
    def test_default_enables_all_packs(self) -> None:
        s = default_service_catalog()
        assert set(s.enabled_packs) == set(ALL_PACKS)
        assert s.featured_pack in s.enabled_packs

    def test_empty_pack_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServiceCatalogStep(enabled_packs=[])

    def test_duplicate_packs_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServiceCatalogStep(
                enabled_packs=["saas_small", "saas_small"],  # type: ignore[list-item]
            )

    def test_featured_must_be_enabled(self) -> None:
        with pytest.raises(ValidationError):
            ServiceCatalogStep(
                enabled_packs=["saas_small"],
                featured_pack="ecommerce_large",  # pas dans enabled_packs
            )

    def test_unknown_pack_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ServiceCatalogStep(enabled_packs=["unknown_pack"])  # type: ignore[list-item]


# ===========================================================================
# Step 4 — Operations Defaults
# ===========================================================================
class TestOperationsDefaultsStep:
    def test_default_sums_to_100(self) -> None:
        o = default_operations()
        total = (o.ai_router_claude_pct + o.ai_router_perplexity_pct
                 + o.ai_router_manus_pct + o.ai_router_internal_pct)
        assert total == 100

    def test_ai_router_not_summing_to_100_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OperationsDefaultsStep(
                hostinger_default_plan="kvm2",
                backup_retention_days=30, refund_sla_hours=72,
                ai_router_claude_pct=50, ai_router_perplexity_pct=20,
                ai_router_manus_pct=20, ai_router_internal_pct=5,  # =95
            )

    def test_backup_retention_below_min_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OperationsDefaultsStep(
                hostinger_default_plan="kvm1",
                backup_retention_days=3,  # < 7
                refund_sla_hours=24,
                ai_router_claude_pct=100, ai_router_perplexity_pct=0,
                ai_router_manus_pct=0, ai_router_internal_pct=0,
            )

    def test_unknown_hostinger_plan_rejected(self) -> None:
        with pytest.raises(ValidationError):
            OperationsDefaultsStep(
                hostinger_default_plan="kvm99",  # type: ignore[arg-type]
                backup_retention_days=30, refund_sla_hours=24,
                ai_router_claude_pct=100, ai_router_perplexity_pct=0,
                ai_router_manus_pct=0, ai_router_internal_pct=0,
            )


# ===========================================================================
# Wizard ordering
# ===========================================================================
class TestStepOrdering:
    def test_canonical_order_is_brand_pricing_services_ops(self) -> None:
        assert WIZARD_STEP_ORDER == (
            StepKey.BRAND_IDENTITY,
            StepKey.PRICING_BASELINE,
            StepKey.SERVICE_CATALOG,
            StepKey.OPERATIONS_DEFAULTS,
        )

    def test_next_step_returns_first_missing(self) -> None:
        assert _next_step(set()) is StepKey.BRAND_IDENTITY
        assert _next_step({StepKey.BRAND_IDENTITY}) is StepKey.PRICING_BASELINE
        assert _next_step(
            {StepKey.BRAND_IDENTITY, StepKey.PRICING_BASELINE}
        ) is StepKey.SERVICE_CATALOG
        # Tous remplis -> dernier
        assert _next_step(set(WIZARD_STEP_ORDER)) is StepKey.OPERATIONS_DEFAULTS


# ===========================================================================
# WizardEngine — DB mockee
# ===========================================================================
class TestWizardEngineLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_in_progress_state(self) -> None:
        pool, conn = _mock_pool()
        wizard_id = uuid4()
        conn.fetchrow.return_value = {
            "wizard_id": wizard_id,
            "started_at": datetime.now(UTC),
        }
        eng = WizardEngine(pool)
        st = await eng.start(started_by="ahmed")
        assert st.wizard_id == wizard_id
        assert st.status is WizardStatus.IN_PROGRESS
        assert st.current_step is StepKey.BRAND_IDENTITY
        assert st.completed_steps == []
        assert st.is_complete is False

    @pytest.mark.asyncio
    async def test_save_step_validates_payload_and_advances(self) -> None:
        pool, conn = _mock_pool()
        wizard_id = uuid4()
        # _fetch_state retourne un wizard initial vide
        conn.fetchrow.return_value = {
            "wizard_id": wizard_id,
            "current_step": StepKey.BRAND_IDENTITY.value,
            "completed_steps": [],
            "partial_config_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "committed_at": None,
        }

        payload = default_brand_identity().model_dump(mode="json")
        eng = WizardEngine(pool)
        new_state = await eng.save_step(
            wizard_id, StepKey.BRAND_IDENTITY, payload,
        )
        assert StepKey.BRAND_IDENTITY in new_state.completed_steps
        assert new_state.current_step is StepKey.PRICING_BASELINE
        # UPDATE a ete appele avec le step suivant
        update_call = conn.execute.await_args_list[0]
        assert "UPDATE setup_wizard_state" in update_call.args[0]

    @pytest.mark.asyncio
    async def test_save_step_invalid_payload_raises(self) -> None:
        pool, conn = _mock_pool()
        eng = WizardEngine(pool)
        with pytest.raises(ValidationError):
            await eng.save_step(
                uuid4(), StepKey.BRAND_IDENTITY,
                {"platform_name": "X"},  # incomplete
            )
        # Aucune ecriture DB
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_step_unknown_wizard_raises_lookup(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eng = WizardEngine(pool)
        with pytest.raises(LookupError):
            await eng.save_step(
                uuid4(), StepKey.BRAND_IDENTITY,
                default_brand_identity().model_dump(mode="json"),
            )

    @pytest.mark.asyncio
    async def test_save_step_already_committed_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "wizard_id": uuid4(),
            "current_step": StepKey.OPERATIONS_DEFAULTS.value,
            "completed_steps": [s.value for s in WIZARD_STEP_ORDER],
            "partial_config_json": {},
            "status": "committed",
            "started_at": datetime.now(UTC),
            "committed_at": datetime.now(UTC),
        }
        eng = WizardEngine(pool)
        with pytest.raises(RuntimeError, match="committed"):
            await eng.save_step(
                uuid4(), StepKey.BRAND_IDENTITY,
                default_brand_identity().model_dump(mode="json"),
            )

    @pytest.mark.asyncio
    async def test_get_state_returns_none_when_missing(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        st = await WizardEngine(pool).get_state(uuid4())
        assert st is None

    @pytest.mark.asyncio
    async def test_get_state_parses_partial_config_string(self) -> None:
        pool, conn = _mock_pool()
        wizard_id = uuid4()
        conn.fetchrow.return_value = {
            "wizard_id": wizard_id,
            "current_step": StepKey.PRICING_BASELINE.value,
            "completed_steps": [StepKey.BRAND_IDENTITY.value],
            "partial_config_json": '{"brand_identity": {"x": 1}}',
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "committed_at": None,
        }
        st = await WizardEngine(pool).get_state(wizard_id)
        assert st is not None
        assert st.partial_config == {"brand_identity": {"x": 1}}


class TestWizardCommit:
    def _full_partial_config(self) -> dict:
        return {
            StepKey.BRAND_IDENTITY.value:
                default_brand_identity().model_dump(mode="json"),
            StepKey.PRICING_BASELINE.value:
                default_pricing_baseline().model_dump(mode="json"),
            StepKey.SERVICE_CATALOG.value:
                default_service_catalog().model_dump(mode="json"),
            StepKey.OPERATIONS_DEFAULTS.value:
                default_operations().model_dump(mode="json"),
        }

    @pytest.mark.asyncio
    async def test_commit_succeeds_when_complete(self) -> None:
        pool, conn = _mock_pool()
        wizard_id = uuid4()
        # 1er fetchrow = _fetch_state (etat complet)
        # 2eme fetchrow = INSERT platform_config RETURNING version
        conn.fetchrow.side_effect = [
            {
                "wizard_id": wizard_id,
                "current_step": StepKey.OPERATIONS_DEFAULTS.value,
                "completed_steps": [s.value for s in WIZARD_STEP_ORDER],
                "partial_config_json": self._full_partial_config(),
                "status": "in_progress",
                "started_at": datetime.now(UTC),
                "committed_at": None,
            },
            {"version": 1},
        ]
        cfg = await WizardEngine(pool).commit(wizard_id)
        assert isinstance(cfg, PlatformConfig)
        assert cfg.version == 1
        # UPDATE pour passer le wizard en 'committed'
        last_execute_sql = conn.execute.await_args_list[-1].args[0]
        assert "status = 'committed'" in last_execute_sql

    @pytest.mark.asyncio
    async def test_commit_incomplete_raises_not_ready(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "wizard_id": uuid4(),
            "current_step": StepKey.PRICING_BASELINE.value,
            "completed_steps": [StepKey.BRAND_IDENTITY.value],
            "partial_config_json": {
                StepKey.BRAND_IDENTITY.value:
                    default_brand_identity().model_dump(mode="json")
            },
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "committed_at": None,
        }
        with pytest.raises(WizardNotReadyError) as exc_info:
            await WizardEngine(pool).commit(uuid4())
        # Le message liste les etapes manquantes
        msg = str(exc_info.value)
        assert "pricing_baseline" in msg
        assert "service_catalog" in msg
        assert "operations_defaults" in msg

    @pytest.mark.asyncio
    async def test_commit_already_committed_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "wizard_id": uuid4(),
            "current_step": StepKey.OPERATIONS_DEFAULTS.value,
            "completed_steps": [s.value for s in WIZARD_STEP_ORDER],
            "partial_config_json": self._full_partial_config(),
            "status": "committed",
            "started_at": datetime.now(UTC),
            "committed_at": datetime.now(UTC),
        }
        with pytest.raises(RuntimeError, match="deja commit"):
            await WizardEngine(pool).commit(uuid4())

    @pytest.mark.asyncio
    async def test_commit_unknown_wizard_raises_lookup(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await WizardEngine(pool).commit(uuid4())

    @pytest.mark.asyncio
    async def test_abandon_returns_true_when_in_progress(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"wizard_id": uuid4()}
        ok = await WizardEngine(pool).abandon(uuid4(), reason="test")
        assert ok is True

    @pytest.mark.asyncio
    async def test_abandon_returns_false_when_not_in_progress(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        ok = await WizardEngine(pool).abandon(uuid4())
        assert ok is False


# ===========================================================================
# WizardState convenience
# ===========================================================================
class TestWizardStateConvenience:
    def test_is_complete_when_all_steps_present(self) -> None:
        st = WizardState(
            wizard_id=uuid4(),
            current_step=StepKey.OPERATIONS_DEFAULTS,
            completed_steps=list(WIZARD_STEP_ORDER),
            partial_config={},
            status=WizardStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            committed_at=None,
        )
        assert st.is_complete is True

    def test_is_not_complete_when_missing(self) -> None:
        st = WizardState(
            wizard_id=uuid4(),
            current_step=StepKey.PRICING_BASELINE,
            completed_steps=[StepKey.BRAND_IDENTITY],
            partial_config={},
            status=WizardStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            committed_at=None,
        )
        assert st.is_complete is False


# ===========================================================================
# Integration : un wizard complet round-trip via mocks
# ===========================================================================
@pytest.mark.asyncio
async def test_full_wizard_roundtrip_with_mocks() -> None:
    """Simule start -> save x4 -> commit, et verifie que la version finale est 1."""
    pool, conn = _mock_pool()
    wizard_id = uuid4()
    state_so_far: dict[str, object] = {
        "wizard_id": wizard_id,
        "current_step": StepKey.BRAND_IDENTITY.value,
        "completed_steps": [],
        "partial_config_json": {},
        "status": "in_progress",
        "started_at": datetime.now(UTC),
        "committed_at": None,
    }

    # fetchrow appelee a chaque save_step (fetch_state) puis a start (return UUID)
    fetchrow_calls: list[dict[str, object] | None] = [
        {"wizard_id": wizard_id, "started_at": datetime.now(UTC)},  # start
    ]

    # Pour chaque save_step on renvoie l'etat a jour, puis on l'enrichit
    payloads = [
        (StepKey.BRAND_IDENTITY, default_brand_identity()),
        (StepKey.PRICING_BASELINE, default_pricing_baseline()),
        (StepKey.SERVICE_CATALOG, default_service_catalog()),
        (StepKey.OPERATIONS_DEFAULTS, default_operations()),
    ]

    completed: list[str] = []
    partial_config: dict[str, object] = {}
    for step, payload in payloads:
        snapshot = dict(state_so_far)
        snapshot["completed_steps"] = list(completed)
        snapshot["partial_config_json"] = json.dumps(partial_config, default=str)
        fetchrow_calls.append(snapshot)
        completed.append(step.value)
        partial_config[step.value] = payload.model_dump(mode="json")

    # Pour le commit : 1 fetch_state final puis 1 INSERT RETURNING version
    fetchrow_calls.append({
        "wizard_id": wizard_id,
        "current_step": StepKey.OPERATIONS_DEFAULTS.value,
        "completed_steps": [s.value for s in WIZARD_STEP_ORDER],
        "partial_config_json": partial_config,
        "status": "in_progress",
        "started_at": datetime.now(UTC),
        "committed_at": None,
    })
    fetchrow_calls.append({"version": 1})

    conn.fetchrow.side_effect = fetchrow_calls

    eng = WizardEngine(pool)
    started = await eng.start()
    assert started.status is WizardStatus.IN_PROGRESS

    for step, payload in payloads:
        await eng.save_step(wizard_id, step, payload.model_dump(mode="json"))

    cfg = await eng.commit(wizard_id, committed_by="ahmed")
    assert cfg.version == 1
    assert cfg.identity.platform_name == default_brand_identity().platform_name
    assert cfg.pricing.minimum_margin_pct >= 50
    assert "saas_medium" == cfg.services.featured_pack
    assert (
        cfg.operations.ai_router_claude_pct
        + cfg.operations.ai_router_perplexity_pct
        + cfg.operations.ai_router_manus_pct
        + cfg.operations.ai_router_internal_pct
    ) == 100
