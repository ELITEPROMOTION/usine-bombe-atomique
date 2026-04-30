"""Tests Phase 9F — Client Onboarding (6 etapes + projects table)."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.saas_factory.client_onboarding.defaults import (
    sample_branding,
    sample_identity,
    sample_pack_selection,
    sample_project_brief,
    sample_review,
    sample_technical,
)
from app.saas_factory.client_onboarding.onboarding_engine import (
    ONBOARDING_STEP_ORDER,
    ClientStepKey,
    OnboardingEngine,
    OnboardingNotReadyError,
    OnboardingSession,
    OnboardingStatus,
    _next_step,
)
from app.saas_factory.client_onboarding.project_factory import (
    NoopQualificationTrigger,
    ProjectFactory,
    ProjectRecord,
)
from app.saas_factory.client_onboarding.steps import (
    ALL_LOCALES,
    BrandingStep,
    IdentityStep,
    PackSelectionStep,
    ProjectBriefStep,
    ReviewSubmitStep,
    TechnicalPreferencesStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    tx_cm = MagicMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=tx_cm)
    conn.fetchrow = AsyncMock()
    conn.execute = AsyncMock()
    return pool, conn


# ===========================================================================
# Step schemas
# ===========================================================================
class TestIdentityStep:
    def test_default_loads(self) -> None:
        i = sample_identity()
        assert i.email == "founder@example.com"
        assert i.country == "FR"

    def test_country_must_be_2_letters_upper(self) -> None:
        with pytest.raises(ValidationError):
            IdentityStep(
                email="a@b.com", full_name="Jane Doe",
                company_name="X", country="fr",  # lowercase rejette
                locale="fr", currency="EUR",
            )
        with pytest.raises(ValidationError):
            IdentityStep(
                email="a@b.com", full_name="Jane Doe",
                company_name="X", country="FRA",  # 3 lettres rejette
                locale="fr", currency="EUR",
            )

    def test_short_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IdentityStep(
                email="a@b.com", full_name="X",   # < 2
                company_name="X", country="FR",
                locale="fr", currency="EUR",
            )

    def test_invalid_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            IdentityStep(
                email="not-an-email", full_name="Jane Doe",
                company_name="X", country="FR",
                locale="fr", currency="EUR",
            )


class TestProjectBriefStep:
    def test_default(self) -> None:
        b = sample_project_brief()
        assert len(b.description) >= 30

    def test_short_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ProjectBriefStep(title="Test app", description="too short")

    def test_urgency_level_whitelist(self) -> None:
        with pytest.raises(ValidationError):
            ProjectBriefStep(
                title="Test", description="x" * 50,
                urgency_level="ASAP",  # type: ignore[arg-type]
            )


class TestPackSelectionStep:
    def test_default(self) -> None:
        p = sample_pack_selection()
        assert p.pack_id == "saas_small"
        assert p.accept_estimate is True

    def test_pack_id_required(self) -> None:
        with pytest.raises(ValidationError):
            PackSelectionStep(pack_id="", accept_estimate=True)

    def test_accept_estimate_required(self) -> None:
        with pytest.raises(ValidationError):
            PackSelectionStep(pack_id="saas_small")  # type: ignore[call-arg]


class TestBrandingStep:
    def test_default(self) -> None:
        b = sample_branding()
        assert b.primary_color.startswith("#")

    def test_invalid_color_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BrandingStep(
                primary_color="blue",
                target_audience="audience x",
            )

    def test_logo_url_must_be_https(self) -> None:
        with pytest.raises(ValidationError):
            BrandingStep(
                logo_url="http://insecure.com/logo.svg",
                primary_color="#FFFFFF",
                target_audience="audience x",
            )

    def test_logo_url_optional(self) -> None:
        b = BrandingStep(
            logo_url=None,
            primary_color="#000000",
            target_audience="audience xyz",
        )
        assert b.logo_url is None


class TestTechnicalPreferencesStep:
    def test_default(self) -> None:
        t = sample_technical()
        assert "en" in t.locales_needed

    def test_duplicate_locales_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TechnicalPreferencesStep(
                preferred_stack="auto",
                locales_needed=["en", "en"],
                custom_domain=False,
            )

    def test_unknown_locale_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TechnicalPreferencesStep(
                preferred_stack="auto",
                locales_needed=["zz"],  # type: ignore[list-item]
                custom_domain=False,
            )

    def test_domain_hint_without_custom_domain_rejected(self) -> None:
        with pytest.raises(ValidationError, match="custom_domain"):
            TechnicalPreferencesStep(
                preferred_stack="auto",
                locales_needed=["en"],
                custom_domain=False,
                domain_hint="example.com",
            )

    def test_domain_hint_with_custom_domain_accepted(self) -> None:
        t = TechnicalPreferencesStep(
            preferred_stack="auto",
            locales_needed=["en"],
            custom_domain=True,
            domain_hint="example.com",
        )
        assert t.domain_hint == "example.com"

    def test_no_locales_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TechnicalPreferencesStep(
                preferred_stack="auto",
                locales_needed=[],
                custom_domain=False,
            )


class TestReviewSubmitStep:
    def test_tos_accepted_required(self) -> None:
        with pytest.raises(ValidationError, match="tos_accepted"):
            ReviewSubmitStep(tos_accepted=False, terms_version="2026-04-30")

    def test_default_marketing_optin_false(self) -> None:
        r = ReviewSubmitStep(tos_accepted=True, terms_version="2026-04-30")
        assert r.marketing_opt_in is False

    def test_default_loads(self) -> None:
        r = sample_review()
        assert r.tos_accepted is True


# ===========================================================================
# Engine ordering
# ===========================================================================
class TestEngineOrdering:
    def test_canonical_order(self) -> None:
        assert ONBOARDING_STEP_ORDER == (
            ClientStepKey.IDENTITY,
            ClientStepKey.PROJECT_BRIEF,
            ClientStepKey.PACK_SELECTION,
            ClientStepKey.BRANDING,
            ClientStepKey.TECHNICAL_PREFERENCES,
            ClientStepKey.REVIEW_SUBMIT,
        )

    def test_next_step_first_missing(self) -> None:
        assert _next_step(set()) is ClientStepKey.IDENTITY
        assert _next_step({ClientStepKey.IDENTITY}) is ClientStepKey.PROJECT_BRIEF

    def test_next_step_returns_last_when_all_complete(self) -> None:
        all_done = set(ONBOARDING_STEP_ORDER)
        assert _next_step(all_done) is ClientStepKey.REVIEW_SUBMIT

    def test_all_locales_constant(self) -> None:
        assert "en" in ALL_LOCALES
        assert "fr" in ALL_LOCALES


# ===========================================================================
# OnboardingEngine — DB mockee
# ===========================================================================
class TestOnboardingEngine:
    @pytest.mark.asyncio
    async def test_start_creates_in_progress_session(self) -> None:
        pool, conn = _mock_pool()
        new_id = uuid4()
        conn.fetchrow.return_value = {
            "session_id": new_id, "started_at": datetime.now(UTC),
        }
        eng = OnboardingEngine(pool, enabled_packs=("saas_small",))
        s = await eng.start(owner_email="a@b.com")
        assert s.session_id == new_id
        assert s.status is OnboardingStatus.IN_PROGRESS
        assert s.current_step is ClientStepKey.IDENTITY
        assert s.is_complete is False

    @pytest.mark.asyncio
    async def test_save_step_validates_and_advances(self) -> None:
        pool, conn = _mock_pool()
        sid = uuid4()
        conn.fetchrow.return_value = {
            "session_id": sid,
            "current_step": ClientStepKey.IDENTITY.value,
            "completed_steps": [],
            "partial_data_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None,
            "project_id": None,
        }
        eng = OnboardingEngine(pool)
        new_state = await eng.save_step(
            sid, ClientStepKey.IDENTITY,
            sample_identity().model_dump(mode="json"),
        )
        assert ClientStepKey.IDENTITY in new_state.completed_steps
        assert new_state.current_step is ClientStepKey.PROJECT_BRIEF

    @pytest.mark.asyncio
    async def test_save_step_invalid_payload_raises(self) -> None:
        pool, conn = _mock_pool()
        eng = OnboardingEngine(pool)
        with pytest.raises(ValidationError):
            await eng.save_step(
                uuid4(), ClientStepKey.IDENTITY,
                {"email": "a@b.com"},  # incomplete
            )
        # Aucun fetchrow puisque la validation Pydantic plante avant.
        conn.fetchrow.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_pack_selection_validates_against_enabled_packs(self) -> None:
        pool, conn = _mock_pool()
        sid = uuid4()
        conn.fetchrow.return_value = {
            "session_id": sid,
            "current_step": ClientStepKey.PACK_SELECTION.value,
            "completed_steps": [],
            "partial_data_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None,
            "project_id": None,
        }
        eng = OnboardingEngine(pool, enabled_packs=("saas_small", "saas_medium"))
        # pack hors liste
        with pytest.raises(ValueError, match="enabled_packs"):
            await eng.save_step(
                sid, ClientStepKey.PACK_SELECTION,
                {"pack_id": "ecommerce_small", "accept_estimate": True},
            )

    @pytest.mark.asyncio
    async def test_save_pack_selection_no_filter_when_no_enabled(self) -> None:
        pool, conn = _mock_pool()
        sid = uuid4()
        conn.fetchrow.return_value = {
            "session_id": sid,
            "current_step": ClientStepKey.PACK_SELECTION.value,
            "completed_steps": [],
            "partial_data_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None,
            "project_id": None,
        }
        eng = OnboardingEngine(pool)  # pas d'enabled_packs
        # pack quelconque accepte
        new_state = await eng.save_step(
            sid, ClientStepKey.PACK_SELECTION,
            {"pack_id": "anything", "accept_estimate": True},
        )
        assert ClientStepKey.PACK_SELECTION in new_state.completed_steps

    @pytest.mark.asyncio
    async def test_save_step_unknown_session_raises_lookup(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eng = OnboardingEngine(pool)
        with pytest.raises(LookupError):
            await eng.save_step(
                uuid4(), ClientStepKey.IDENTITY,
                sample_identity().model_dump(mode="json"),
            )

    @pytest.mark.asyncio
    async def test_save_step_already_submitted_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "session_id": uuid4(),
            "current_step": ClientStepKey.REVIEW_SUBMIT.value,
            "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
            "partial_data_json": {},
            "status": "submitted",
            "started_at": datetime.now(UTC),
            "submitted_at": datetime.now(UTC),
            "project_id": uuid4(),
        }
        eng = OnboardingEngine(pool)
        with pytest.raises(RuntimeError):
            await eng.save_step(
                uuid4(), ClientStepKey.IDENTITY,
                sample_identity().model_dump(mode="json"),
            )

    @pytest.mark.asyncio
    async def test_get_state_none_when_missing(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        s = await OnboardingEngine(pool).get_state(uuid4())
        assert s is None

    @pytest.mark.asyncio
    async def test_get_state_parses_string_partial_data(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "session_id": uuid4(),
            "current_step": ClientStepKey.PROJECT_BRIEF.value,
            "completed_steps": [ClientStepKey.IDENTITY.value],
            "partial_data_json": '{"identity": {"email": "a@b.com"}}',
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None,
            "project_id": None,
        }
        s = await OnboardingEngine(pool).get_state(uuid4())
        assert s is not None
        assert s.partial_data == {"identity": {"email": "a@b.com"}}

    @pytest.mark.asyncio
    async def test_abandon_returns_true_when_in_progress(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {"session_id": uuid4()}
        ok = await OnboardingEngine(pool).abandon(uuid4(), reason="user left")
        assert ok is True

    @pytest.mark.asyncio
    async def test_abandon_returns_false_when_not_in_progress(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        ok = await OnboardingEngine(pool).abandon(uuid4())
        assert ok is False

    @pytest.mark.asyncio
    async def test_mark_submitted_persists(self) -> None:
        pool, conn = _mock_pool()
        eng = OnboardingEngine(pool)
        await eng.mark_submitted(uuid4(), project_id=uuid4())
        sql = conn.execute.await_args_list[0].args[0]
        assert "status = 'submitted'" in sql


class TestSessionConvenience:
    def test_is_complete_when_all_steps(self) -> None:
        s = OnboardingSession(
            session_id=uuid4(),
            current_step=ClientStepKey.REVIEW_SUBMIT,
            completed_steps=list(ONBOARDING_STEP_ORDER),
            partial_data={},
            status=OnboardingStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            submitted_at=None, project_id=None,
        )
        assert s.is_complete is True

    def test_is_not_complete_when_missing(self) -> None:
        s = OnboardingSession(
            session_id=uuid4(),
            current_step=ClientStepKey.IDENTITY,
            completed_steps=[],
            partial_data={},
            status=OnboardingStatus.IN_PROGRESS,
            started_at=datetime.now(UTC),
            submitted_at=None, project_id=None,
        )
        assert s.is_complete is False


# ===========================================================================
# ProjectFactory + QualificationTrigger
# ===========================================================================
class TestProjectFactory:
    def _full_partial(self) -> dict:
        return {
            ClientStepKey.IDENTITY.value: sample_identity().model_dump(mode="json"),
            ClientStepKey.PROJECT_BRIEF.value:
                sample_project_brief().model_dump(mode="json"),
            ClientStepKey.PACK_SELECTION.value:
                sample_pack_selection().model_dump(mode="json"),
            ClientStepKey.BRANDING.value:
                sample_branding().model_dump(mode="json"),
            ClientStepKey.TECHNICAL_PREFERENCES.value:
                sample_technical().model_dump(mode="json"),
            ClientStepKey.REVIEW_SUBMIT.value:
                sample_review().model_dump(mode="json"),
        }

    @pytest.mark.asyncio
    async def test_create_from_session_succeeds_and_calls_trigger(self) -> None:
        pool, conn = _mock_pool()
        sid = uuid4()
        proj_id = uuid4()
        # 1er fetchrow : engine.get_state -> session complete
        # 2eme fetchrow : INSERT projects RETURNING
        conn.fetchrow.side_effect = [
            {
                "session_id": sid,
                "current_step": ClientStepKey.REVIEW_SUBMIT.value,
                "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
                "partial_data_json": self._full_partial(),
                "status": "in_progress",
                "started_at": datetime.now(UTC),
                "submitted_at": None, "project_id": None,
            },
            {"project_id": proj_id, "created_at": datetime.now(UTC)},
        ]
        eng = OnboardingEngine(pool)
        trig = NoopQualificationTrigger()
        factory = ProjectFactory(pool, eng, qualification_trigger=trig)
        rec = await factory.create_from_session(sid)
        assert isinstance(rec, ProjectRecord)
        assert rec.project_id == proj_id
        assert rec.pack_id_hint == "saas_small"
        assert rec.owner_email == "founder@example.com"
        # Trigger no-op a ete appele
        assert len(trig.calls) == 1
        assert trig.calls[0]["project_id"] == str(proj_id)

    @pytest.mark.asyncio
    async def test_create_unknown_session_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        eng = OnboardingEngine(pool)
        factory = ProjectFactory(pool, eng)
        with pytest.raises(LookupError):
            await factory.create_from_session(uuid4())

    @pytest.mark.asyncio
    async def test_create_incomplete_session_raises(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = {
            "session_id": uuid4(),
            "current_step": ClientStepKey.PROJECT_BRIEF.value,
            "completed_steps": [ClientStepKey.IDENTITY.value],
            "partial_data_json": {},
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None, "project_id": None,
        }
        eng = OnboardingEngine(pool)
        factory = ProjectFactory(pool, eng)
        with pytest.raises(OnboardingNotReadyError) as exc_info:
            await factory.create_from_session(uuid4())
        assert "project_brief" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_already_has_project_raises(self) -> None:
        pool, conn = _mock_pool()
        existing_proj = uuid4()
        conn.fetchrow.return_value = {
            "session_id": uuid4(),
            "current_step": ClientStepKey.REVIEW_SUBMIT.value,
            "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
            "partial_data_json": self._full_partial(),
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None,
            "project_id": existing_proj,
        }
        eng = OnboardingEngine(pool)
        factory = ProjectFactory(pool, eng)
        with pytest.raises(RuntimeError, match="deja un projet"):
            await factory.create_from_session(uuid4())

    @pytest.mark.asyncio
    async def test_default_trigger_is_noop(self) -> None:
        pool, conn = _mock_pool()
        sid = uuid4()
        proj_id = uuid4()
        conn.fetchrow.side_effect = [
            {
                "session_id": sid,
                "current_step": ClientStepKey.REVIEW_SUBMIT.value,
                "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
                "partial_data_json": self._full_partial(),
                "status": "in_progress",
                "started_at": datetime.now(UTC),
                "submitted_at": None, "project_id": None,
            },
            {"project_id": proj_id, "created_at": datetime.now(UTC)},
        ]
        eng = OnboardingEngine(pool)
        # Pas de trigger fourni : default = NoopQualificationTrigger
        factory = ProjectFactory(pool, eng)
        rec = await factory.create_from_session(sid)
        assert rec.project_id == proj_id


def test_noop_trigger_records_calls() -> None:
    import asyncio
    trig = NoopQualificationTrigger()
    proj = uuid4()
    asyncio.run(trig(
        project_id=proj, cdc_text="hello world",
        owner_email="x@y.z", metadata={"k": "v"},
    ))
    assert len(trig.calls) == 1
    assert trig.calls[0]["cdc_text_len"] == len("hello world")
    assert trig.calls[0]["metadata"] == {"k": "v"}


# ===========================================================================
# Integration : roundtrip start -> 6 saves -> create_from_session
# ===========================================================================
@pytest.mark.asyncio
async def test_full_onboarding_roundtrip() -> None:
    pool, conn = _mock_pool()
    sid = uuid4()
    proj_id = uuid4()

    # Programme : start, save x6, create_from_session
    fetchrow_seq: list = [
        # start
        {"session_id": sid, "started_at": datetime.now(UTC)},
    ]
    completed: list[str] = []
    partial: dict = {}
    payloads = [
        (ClientStepKey.IDENTITY, sample_identity()),
        (ClientStepKey.PROJECT_BRIEF, sample_project_brief()),
        (ClientStepKey.PACK_SELECTION, sample_pack_selection()),
        (ClientStepKey.BRANDING, sample_branding()),
        (ClientStepKey.TECHNICAL_PREFERENCES, sample_technical()),
        (ClientStepKey.REVIEW_SUBMIT, sample_review()),
    ]
    for step, payload in payloads:
        snapshot = {
            "session_id": sid,
            "current_step": step.value,
            "completed_steps": list(completed),
            "partial_data_json": json.dumps(partial, default=str),
            "status": "in_progress",
            "started_at": datetime.now(UTC),
            "submitted_at": None, "project_id": None,
        }
        fetchrow_seq.append(snapshot)
        completed.append(step.value)
        partial[step.value] = payload.model_dump(mode="json")

    # create_from_session : get_state retourne la session complete + INSERT projects
    fetchrow_seq.append({
        "session_id": sid,
        "current_step": ClientStepKey.REVIEW_SUBMIT.value,
        "completed_steps": [s.value for s in ONBOARDING_STEP_ORDER],
        "partial_data_json": partial,
        "status": "in_progress",
        "started_at": datetime.now(UTC),
        "submitted_at": None, "project_id": None,
    })
    fetchrow_seq.append({"project_id": proj_id, "created_at": datetime.now(UTC)})

    conn.fetchrow.side_effect = fetchrow_seq

    eng = OnboardingEngine(pool, enabled_packs=("saas_small",))
    started = await eng.start()
    assert started.status is OnboardingStatus.IN_PROGRESS

    for step, payload in payloads:
        await eng.save_step(sid, step, payload.model_dump(mode="json"))

    factory = ProjectFactory(pool, eng)
    rec = await factory.create_from_session(sid)
    assert rec.project_id == proj_id
    assert rec.title == sample_project_brief().title
    assert rec.summary["identity"]["email"] == "founder@example.com"
