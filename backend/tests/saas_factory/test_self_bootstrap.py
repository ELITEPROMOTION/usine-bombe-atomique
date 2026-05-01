"""Tests Phase 9-BOOT — modules self_bootstrap (logique pure + DB mockee)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.saas_factory.self_bootstrap.handoff_kyc_orchestrator import (
    DEFAULT_EXPIRY,
    REMINDER_SCHEDULE,
    TEMPLATES,
    HandoffKycOrchestrator,
    HandoffStatus,
    HandoffType,
    _build_magic_link,
    _new_token,
)
from app.saas_factory.self_bootstrap.mandate_engine import (
    ZERO_HASH,
    MandateType,
    _compute_chain_hash,
    _compute_payload_hash,
)
from app.saas_factory.self_bootstrap.minimal_apis_validator import (
    SERVICE_SPECS,
    MinimalApisValidator,
)
from app.saas_factory.self_bootstrap.service_priority_queue import (
    DEFAULT_CATALOG,
    ServiceDescriptor,
    ServicePriorityQueue,
    ServiceTier,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------
def _good_env() -> dict[str, str]:
    return {
        "ANTHROPIC_API_KEY": "sk-ant-" + "a" * 50,
        "MANUS_API_KEY": "sk-" + "b" * 30,
        "PERPLEXITY_API_KEY": "pplx-" + "c" * 30,
        "HOSTINGER_API_TOKEN": "d" * 30,
    }


# ===========================================================================
# minimal_apis_validator
# ===========================================================================
class TestMinimalApisValidator:
    def test_all_four_secrets_present_and_format_ok(self) -> None:
        validator = MinimalApisValidator(env=_good_env())
        out = validator.validate()
        assert out.all_present is True
        assert out.all_format_ok is True
        assert set(out.services) == {"anthropic", "manus", "perplexity", "hostinger"}
        for chk in out.services.values():
            assert chk.present is True
            assert chk.format_ok is True
            assert chk.connectivity == "unknown"
        # is_pass(False) car connectivite non testee
        assert out.is_pass(require_connectivity=False) is True
        assert out.is_pass(require_connectivity=True) is False

    def test_missing_secret_marks_service_absent(self) -> None:
        env = _good_env()
        del env["ANTHROPIC_API_KEY"]
        out = MinimalApisValidator(env=env).validate()
        assert out.all_present is False
        assert out.services["anthropic"].present is False
        assert out.services["anthropic"].format_ok is False
        # autres services intacts
        assert out.services["manus"].present is True

    def test_bad_prefix_marks_format_invalid(self) -> None:
        env = _good_env()
        env["ANTHROPIC_API_KEY"] = "wrong-prefix-" + "x" * 50
        out = MinimalApisValidator(env=env).validate()
        assert out.all_present is True
        assert out.all_format_ok is False
        assert out.services["anthropic"].format_ok is False
        assert "prefixe attendu" in out.services["anthropic"].message

    def test_too_short_marks_format_invalid(self) -> None:
        env = _good_env()
        env["MANUS_API_KEY"] = "sk-short"
        out = MinimalApisValidator(env=env).validate()
        assert out.services["manus"].format_ok is False
        assert "trop court" in out.services["manus"].message

    def test_secret_value_never_logged_or_returned_full(self) -> None:
        env = _good_env()
        out = MinimalApisValidator(env=env).validate()
        full = env["ANTHROPIC_API_KEY"]
        chk = out.services["anthropic"]
        assert full not in chk.masked_hint
        assert full not in chk.message
        # hint = '...XXXX' (4 derniers caracteres)
        assert chk.masked_hint.startswith("...")
        assert len(chk.masked_hint) == 7

    def test_summary_returns_serializable_dict(self) -> None:
        out = MinimalApisValidator(env=_good_env()).validate()
        summary = out.summary()
        assert "anthropic" in summary
        assert summary["anthropic"]["present"] is True
        assert isinstance(summary["anthropic"]["format_ok"], bool)

    def test_known_service_specs_cover_4_required(self) -> None:
        assert set(SERVICE_SPECS) == {
            "anthropic", "manus", "perplexity", "hostinger",
        }


# ===========================================================================
# mandate_engine — fonctions pures
# ===========================================================================
class TestMandateChainPure:
    def test_payload_hash_is_deterministic(self) -> None:
        ts = datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)
        scope = {"service": "stripe", "tier": 3}
        h1 = _compute_payload_hash(
            mandate_type=MandateType.ACCOUNT_CREATION,
            principal_id="user-1",
            agent_identity="uba_platform",
            scope=scope,
            signed_at=ts,
        )
        h2 = _compute_payload_hash(
            mandate_type=MandateType.ACCOUNT_CREATION,
            principal_id="user-1",
            agent_identity="uba_platform",
            scope=scope,
            signed_at=ts,
        )
        assert h1 == h2
        assert len(h1) == 64

    def test_chain_hash_links_with_prev(self) -> None:
        chain1 = _compute_chain_hash(ZERO_HASH, "a" * 64)
        chain2 = _compute_chain_hash(chain1, "b" * 64)
        assert chain1 != chain2
        # Modifier prev change le resultat
        chain1_alt = _compute_chain_hash("0" * 63 + "1", "a" * 64)
        assert chain1 != chain1_alt

    def test_zero_hash_is_64_zeros(self) -> None:
        assert ZERO_HASH == "0" * 64
        assert len(ZERO_HASH) == 64


# ===========================================================================
# mandate_engine — chemins DB (pool mocke)
# ===========================================================================
class TestMandateEngineDB:
    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        pool = MagicMock()
        conn = MagicMock()
        # async context managers
        acquire_cm = MagicMock()
        acquire_cm.__aenter__ = AsyncMock(return_value=conn)
        acquire_cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=acquire_cm)

        tx_cm = MagicMock()
        tx_cm.__aenter__ = AsyncMock(return_value=None)
        tx_cm.__aexit__ = AsyncMock(return_value=None)
        conn.transaction = MagicMock(return_value=tx_cm)
        return pool

    @pytest.mark.asyncio
    async def test_issue_first_mandate_uses_zero_hash(self, mock_pool: MagicMock) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        # fetchrow pour _last_chain_hash : aucun mandat preexistant
        conn.fetchrow = AsyncMock(side_effect=[
            None,
            {
                "mandate_id": uuid4(),
                "signed_at": datetime.now(UTC),
            },
        ])

        engine = MandateEngine(mock_pool)
        mandate = await engine.issue(
            mandate_type=MandateType.ACCOUNT_CREATION,
            principal_id="p1",
            agent_identity="uba_platform",
            scope={"service": "cloudflare"},
        )
        assert mandate.prev_hash == ZERO_HASH
        assert len(mandate.chain_hash) == 64
        assert mandate.chain_hash != ZERO_HASH
        assert mandate.is_active is True

    @pytest.mark.asyncio
    async def test_issue_chains_to_previous(self, mock_pool: MagicMock) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        prev_chain = "f" * 64
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow = AsyncMock(side_effect=[
            {"chain_hash": prev_chain},
            {"mandate_id": uuid4(), "signed_at": datetime.now(UTC)},
        ])
        engine = MandateEngine(mock_pool)
        m = await engine.issue(
            mandate_type=MandateType.SUB_AUTHORIZATION,
            principal_id="p2",
            agent_identity="uba_platform",
            scope={"x": 1},
        )
        assert m.prev_hash == prev_chain
        # chain_hash = sha256(prev + payload)
        assert m.chain_hash == _compute_chain_hash(prev_chain, m.payload_hash)


# ===========================================================================
# service_priority_queue
# ===========================================================================
class TestServicePriorityQueue:
    def test_tier1_services_come_first(self) -> None:
        q = ServicePriorityQueue()
        first = q.next()
        assert first is not None
        assert first.tier is ServiceTier.NO_KYC

    def test_dependencies_block_until_ancestors_active(self) -> None:
        catalog = (
            ServiceDescriptor("a", ServiceTier.NO_KYC),
            ServiceDescriptor("b", ServiceTier.NO_KYC, depends_on=("a",)),
        )
        q = ServicePriorityQueue(catalog)
        first = q.next()
        assert first is not None
        assert first.name == "a"
        # b ne doit pas sortir tant que a n'est pas active
        # mais next() peut le re-pousser : on simule
        second = q.next()
        # second peut etre None (b bloque par dep) ou b si a deja release : ici a pas marque
        assert second is None
        q.mark_success("a")
        third = q.next()
        assert third is not None
        assert third.name == "b"

    def test_stripe_depends_on_cloudflare_and_resend_in_default_catalog(self) -> None:
        stripe = next(s for s in DEFAULT_CATALOG if s.name == "stripe")
        assert "cloudflare" in stripe.depends_on
        assert "resend" in stripe.depends_on
        assert stripe.tier is ServiceTier.KYC_BUSINESS

    def test_failure_then_retry_with_backoff(self) -> None:
        clock = [1000.0]
        q = ServicePriorityQueue(clock=lambda: clock[0])
        svc = q.next()
        assert svc is not None
        retry = q.mark_failure(svc.name, "transient")
        assert retry is True
        # Pas pret avant backoff
        assert q._items[svc.name].next_run_at > 1000.0
        # Avancer le clock au-dela du backoff
        clock[0] = q._items[svc.name].next_run_at + 0.1
        again = q.next()
        assert again is not None  # peut etre meme service ou autre tier1

    def test_three_identical_failures_triggers_loop_detection(self) -> None:
        q = ServicePriorityQueue()
        svc = q.next()
        assert svc is not None
        assert q.mark_failure(svc.name, "same-error") is True
        assert q.mark_failure(svc.name, "same-error") is True
        # 3eme echec identique -> loop -> abandon
        assert q.mark_failure(svc.name, "same-error") is False
        st = q.status()[svc.name]
        assert st["failed_permanent"] is True

    def test_max_attempts_exhaustion(self) -> None:
        catalog = (ServiceDescriptor("only", ServiceTier.NO_KYC, max_attempts=2),)
        q = ServicePriorityQueue(catalog)
        q.next()
        # 1ere tentative -> attempt=1, retry True
        assert q.mark_failure("only", "err1") is True
        # 2eme tentative differente -> attempt=2 == max -> abandon
        assert q.mark_failure("only", "err2") is False

    def test_status_reports_per_service(self) -> None:
        q = ServicePriorityQueue()
        st = q.status()
        assert "cloudflare" in st
        assert st["cloudflare"]["activated"] is False
        q.mark_success("cloudflare")
        st = q.status()
        assert st["cloudflare"]["activated"] is True

    def test_completion_when_all_done(self) -> None:
        catalog = (
            ServiceDescriptor("a", ServiceTier.NO_KYC),
            ServiceDescriptor("b", ServiceTier.NO_KYC),
        )
        q = ServicePriorityQueue(catalog)
        q.mark_success("a")
        q.mark_success("b")
        assert q.is_complete is True


# ===========================================================================
# handoff_kyc_orchestrator — purs
# ===========================================================================
class TestHandoffPure:
    def test_token_is_url_safe_and_long(self) -> None:
        t = _new_token()
        assert len(t) >= 32
        # urlsafe : pas de + ou /
        assert "+" not in t
        assert "/" not in t

    def test_magic_link_includes_token(self) -> None:
        link = _build_magic_link("https://app.uba.studio/", "abc123")
        assert link == "https://app.uba.studio/handoff/abc123"

    def test_templates_present_for_all_types_and_locales(self) -> None:
        for handoff_type in ("kyc", "card", "manual_step"):
            for locale in ("en", "fr"):
                tpl = TEMPLATES[handoff_type][locale]
                assert "subject" in tpl
                assert "body" in tpl
                # placeholders requis
                assert "{service}" in tpl["subject"] or "{service}" in tpl["body"]
                assert "{magic_link}" in tpl["body"]
                assert "{expires_at}" in tpl["body"]

    def test_reminder_schedule_is_strictly_increasing(self) -> None:
        deltas = [d for d, _ in REMINDER_SCHEDULE]
        assert deltas == sorted(deltas)
        assert REMINDER_SCHEDULE[0][1] == HandoffStatus.REMINDED_1H
        assert REMINDER_SCHEDULE[-1][1] == HandoffStatus.REMINDED_24H

    def test_default_expiry_reasonable(self) -> None:
        assert timedelta(hours=1) < DEFAULT_EXPIRY < timedelta(days=10)


# ===========================================================================
# handoff_kyc_orchestrator — DB mockee
# ===========================================================================
class TestHandoffDB:
    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        pool = MagicMock()
        conn = MagicMock()
        conn.fetchrow = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.execute = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=cm)
        return pool

    @pytest.mark.asyncio
    async def test_open_handoff_kyc_persists_and_returns_envelope(
        self, mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        new_id = uuid4()
        conn.fetchrow.return_value = {"handoff_id": new_id}

        orch = HandoffKycOrchestrator(mock_pool, base_url="https://t.example")
        env = await orch.open_handoff(
            handoff_type=HandoffType.KYC,
            target_email="ahmed@example.com",
            service="stripe",
            locale="fr",
        )
        assert env.handoff_id == new_id
        assert env.locale == "fr"
        assert "stripe" in env.subject.lower()
        assert env.magic_link.startswith("https://t.example/handoff/")
        # INSERT a bien ete tente
        conn.fetchrow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_open_handoff_invalid_locale_falls_back_to_en(
        self, mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.return_value = {"handoff_id": uuid4()}
        orch = HandoffKycOrchestrator(mock_pool)
        env = await orch.open_handoff(
            handoff_type=HandoffType.CARD,
            target_email="x@x.com",
            service="datadog",
            locale="zz",  # locale invalide
        )
        assert env.locale == "en"

    @pytest.mark.asyncio
    async def test_resolve_returns_true_when_found(self, mock_pool: MagicMock) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.return_value = {"handoff_id": uuid4()}
        orch = HandoffKycOrchestrator(mock_pool)
        assert await orch.resolve("token-x") is True

    @pytest.mark.asyncio
    async def test_resolve_returns_false_when_not_found(
        self, mock_pool: MagicMock,
    ) -> None:
        conn = mock_pool.acquire.return_value.__aenter__.return_value
        conn.fetchrow.return_value = None
        orch = HandoffKycOrchestrator(mock_pool)
        assert await orch.resolve("nope") is False


# ===========================================================================
# account_creator_orchestrator — plan_all sur DB mockee
# ===========================================================================
class TestAccountCreatorPlan:
    @pytest.mark.asyncio
    async def test_plan_all_produces_steps_in_tier_order(self) -> None:
        from app.saas_factory.self_bootstrap.account_creator_orchestrator import (
            AccountCreatorOrchestrator,
            StepKind,
        )
        from app.saas_factory.self_bootstrap.handoff_kyc_orchestrator import (
            HandoffEnvelope,
        )
        from app.saas_factory.self_bootstrap.mandate_engine import Mandate

        pool = MagicMock()
        conn = MagicMock()
        conn.execute = AsyncMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=None)
        pool.acquire = MagicMock(return_value=cm)

        # Mocks pour mandate engine + handoff orch
        mandate_engine = MagicMock()
        mandate_engine.issue = AsyncMock(side_effect=lambda **kw: Mandate(
            mandate_id=uuid4(),
            mandate_type=kw["mandate_type"],
            principal_id=kw["principal_id"],
            agent_identity=kw["agent_identity"],
            scope=kw["scope"],
            payload_hash="p" * 64,
            prev_hash=ZERO_HASH,
            chain_hash="c" * 64,
            signed_at=datetime.now(UTC),
            expires_at=None,
            revoked_at=None,
            revocation_reason=None,
            audit_log=[],
        ))
        handoff = MagicMock()
        handoff.open_handoff = AsyncMock(side_effect=lambda **kw: HandoffEnvelope(
            handoff_id=uuid4(),
            type=kw["handoff_type"],
            target_email=kw["target_email"],
            magic_link="https://x/handoff/y",
            subject="s", body="b", locale=kw.get("locale", "en"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ))

        orch = AccountCreatorOrchestrator(pool, mandate_engine, handoff)
        plan = await orch.plan_all(
            principal_id="ahmed",
            target_email="ahmed@example.com",
            locale="fr",
        )

        # Tous les services du catalogue par defaut sont presents
        names = [s.service for s in plan.steps]
        assert set(names) == {s.name for s in DEFAULT_CATALOG}

        # Ordre par tier croissant : pas de tier 2/3 avant tous les tier 1
        tiers = [int(s.tier) for s in plan.steps]
        first_tier2 = next((i for i, t in enumerate(tiers) if t >= 2), len(tiers))
        assert all(t == 1 for t in tiers[:first_tier2])

        # tier 2/3 ont des handoffs ; tier 1 = automated sans handoff
        for step in plan.steps:
            if step.tier == ServiceTier.NO_KYC:
                assert step.kind is StepKind.AUTOMATED
                assert step.handoff_id is None
            else:
                assert step.handoff_id is not None
                assert step.kind in (StepKind.REQUIRES_CARD, StepKind.REQUIRES_KYC)

        # mandates emis pour chaque service
        assert mandate_engine.issue.await_count == len(DEFAULT_CATALOG)


# ===========================================================================
# mandate_engine — revoke / get / verify_chain (DB mockee)
# ===========================================================================
def _mock_pool_with_conn() -> tuple[MagicMock, MagicMock]:
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


class TestMandateRevokeGetVerify:
    @pytest.mark.asyncio
    async def test_revoke_returns_mandate_with_revocation_marked(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        mid = uuid4()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {
            "mandate_id": mid,
            "mandate_type": "account_creation",
            "principal_id": "p",
            "agent_identity": "uba_platform",
            "scope_json": {"s": "stripe"},
            "payload_hash": "p" * 64,
            "prev_hash": "0" * 64,
            "chain_hash": "c" * 64,
            "signed_at": now - timedelta(days=1),
            "expires_at": None,
            "revoked_at": now,
            "revocation_reason": "test",
            "audit_log": [{"event": "issued"}, {"event": "revoked"}],
        }
        m = await MandateEngine(pool).revoke(mid, reason="test")
        assert m.mandate_id == mid
        assert m.revoked_at == now
        assert m.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_raises_when_not_found_or_already_revoked(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        conn.fetchrow.return_value = None
        with pytest.raises(LookupError):
            await MandateEngine(pool).revoke(uuid4(), reason="x")

    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        conn.fetchrow.return_value = None
        m = await MandateEngine(pool).get(uuid4())
        assert m is None

    @pytest.mark.asyncio
    async def test_get_returns_mandate_when_present(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        # Test du chemin _row_to_mandate avec audit_log/scope_json en string JSON
        conn.fetchrow.return_value = {
            "mandate_id": uuid4(),
            "mandate_type": "data_processing",
            "principal_id": "p",
            "agent_identity": "uba_platform",
            "scope_json": '{"a":1}',  # str -> doit etre json.loads-e
            "payload_hash": "p" * 64,
            "prev_hash": "0" * 64,
            "chain_hash": "c" * 64,
            "signed_at": datetime.now(UTC),
            "expires_at": None,
            "revoked_at": None,
            "revocation_reason": None,
            "audit_log": '[{"event":"issued"}]',
        }
        m = await MandateEngine(pool).get(uuid4())
        assert m is not None
        assert m.scope == {"a": 1}
        assert m.audit_log == [{"event": "issued"}]
        assert m.is_active is True

    @pytest.mark.asyncio
    async def test_verify_chain_empty_is_valid(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        conn.fetch.return_value = []
        out = await MandateEngine(pool).verify_chain()
        assert out == {"valid": True, "checked": 0, "first_break": None}

    @pytest.mark.asyncio
    async def test_verify_chain_detects_consistent_chain(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        # Construire 2 maillons coherents
        ph1, ph2 = "a" * 64, "b" * 64
        ch1 = _compute_chain_hash(ZERO_HASH, ph1)
        ch2 = _compute_chain_hash(ch1, ph2)
        conn.fetch.return_value = [
            {"id": 1, "payload_hash": ph1, "prev_hash": ZERO_HASH, "chain_hash": ch1},
            {"id": 2, "payload_hash": ph2, "prev_hash": ch1, "chain_hash": ch2},
        ]
        out = await MandateEngine(pool).verify_chain()
        assert out["valid"] is True
        assert out["checked"] == 2

    @pytest.mark.asyncio
    async def test_verify_chain_detects_tampering(self) -> None:
        from app.saas_factory.self_bootstrap.mandate_engine import MandateEngine
        pool, conn = _mock_pool_with_conn()
        ph1 = "a" * 64
        ch1 = _compute_chain_hash(ZERO_HASH, ph1)
        # 2eme maillon altere : chain_hash ne correspond pas au calcul
        conn.fetch.return_value = [
            {"id": 1, "payload_hash": ph1, "prev_hash": ZERO_HASH, "chain_hash": ch1},
            {
                "id": 2,
                "payload_hash": "b" * 64,
                "prev_hash": ch1,
                "chain_hash": "TAMPERED" * 8,  # 64 chars mais faux
            },
        ]
        out = await MandateEngine(pool).verify_chain(limit=10)
        assert out["valid"] is False
        assert out["first_break"] == 2


# ===========================================================================
# minimal_apis_validator — chemin connectivite (socket mocke)
# ===========================================================================
class TestValidatorConnectivity:
    def test_connectivity_check_passes_when_socket_succeeds(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # On simule un socket qui se connecte sans erreur.
        class _FakeSock:
            def __enter__(self): return self
            def __exit__(self, *_): return None

        from app.saas_factory.self_bootstrap import minimal_apis_validator as mod
        monkeypatch.setattr(mod.socket, "create_connection", lambda *a, **kw: _FakeSock())

        out = MinimalApisValidator(env=_good_env()).validate(check_connectivity=True)
        assert out.all_reachable is True
        for chk in out.services.values():
            assert chk.connectivity == "ok"
        assert out.is_pass(require_connectivity=True) is True

    def test_connectivity_check_fails_when_socket_errors(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from app.saas_factory.self_bootstrap import minimal_apis_validator as mod

        def _boom(*_a, **_kw):
            raise OSError("network down")
        monkeypatch.setattr(mod.socket, "create_connection", _boom)

        out = MinimalApisValidator(env=_good_env()).validate(
            check_connectivity=True, timeout=0.5,
        )
        assert out.all_reachable is False
        for chk in out.services.values():
            assert chk.connectivity == "fail"
        assert out.is_pass(require_connectivity=True) is False


# ===========================================================================
# handoff_kyc_orchestrator — tick + email_sender
# ===========================================================================
class TestHandoffTick:
    @pytest.mark.asyncio
    async def test_tick_returns_zero_when_db_empty(self) -> None:
        pool, conn = _mock_pool_with_conn()
        conn.fetch.return_value = []
        orch = HandoffKycOrchestrator(pool)
        result = await orch.tick()
        assert result == {"reminders_sent": 0, "escalated": 0, "expired": 0}

    @pytest.mark.asyncio
    async def test_open_handoff_calls_email_sender_when_provided(self) -> None:
        pool, conn = _mock_pool_with_conn()
        conn.fetchrow.return_value = {"handoff_id": uuid4()}

        sent: list[dict[str, str]] = []

        class _Sender:
            async def send(self, *, to: str, subject: str, body: str) -> None:
                sent.append({"to": to, "subject": subject, "body": body})

        orch = HandoffKycOrchestrator(pool, email_sender=_Sender())
        await orch.open_handoff(
            handoff_type=HandoffType.MANUAL_STEP,
            target_email="x@example.com",
            service="github",
            locale="en",
        )
        assert len(sent) == 1
        assert sent[0]["to"] == "x@example.com"
        assert "github" in sent[0]["subject"]
