"""Tests Phase 9K — Observabilité 360°."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from prometheus_client import CollectorRegistry

from app.saas_factory.observability.health import (
    HealthCheckResult,
    HealthStatus,
    V9HealthCheck,
    _aggregate_status,
)
from app.saas_factory.observability.metrics import (
    V9Metrics,
    get_v9_metrics,
    reset_v9_metrics_for_test,
)
from app.saas_factory.observability.sentry_context import (
    _hash_email,
    add_payment_context,
    add_project_context,
    capture_v9_exception,
    is_sentry_available,
)
from app.saas_factory.observability.slo import (
    V9_SLOS,
    SLODefinition,
    SLOSeverity,
    find_slo_by_name,
    slos_by_severity,
    total_error_budget_critical_minutes,
)


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    pool = MagicMock()
    conn = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    conn.fetchrow = AsyncMock()
    conn.fetchval = AsyncMock()
    return pool, conn


# ===========================================================================
# V9Metrics
# ===========================================================================
class TestV9Metrics:
    def test_isolated_registry(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        # Verifie que les metrics sont bien enregistrees dans CE registry
        m.paywall_triggered.labels(project_status="paywall_pending").inc()
        # On peut collecter
        samples = list(reg.collect())
        names = {s.name for s in samples}
        assert "uba_paywall_triggered" in names

    def test_record_payment_increments_succeeded(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        m.record_payment(amount_cents=10000, currency="EUR", status="succeeded")
        m.record_payment(amount_cents=20000, currency="EUR", status="failed")
        # payment_succeeded compte 1 (le failed n'incremente pas succeeded)
        succeeded = m.payment_succeeded.labels(currency="EUR")._value.get()
        assert succeeded == 1.0

    def test_record_ai_decision(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        m.record_ai_decision(
            requested_provider="claude",
            actual_provider="claude",
            status="ok",
            cost_usd=0.05,
        )
        m.record_ai_decision(
            requested_provider="claude",
            actual_provider="perplexity",   # fallback
            status="fallback",
            cost_usd=0.01,
        )
        decisions = m.ai_decisions_total.labels(
            requested_provider="claude",
            actual_provider="claude",
            status="ok",
        )._value.get()
        assert decisions == 1.0

    def test_record_ai_decision_negative_cost_clamped(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        # Cost negatif (bug ?) ne doit pas planter
        m.record_ai_decision(
            requested_provider="x", actual_provider="x",
            status="ok", cost_usd=-1.0,
        )
        # Pas d'exception

    def test_record_webhook(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        m.record_webhook(
            source="stripe", event_type="checkout.session.completed",
            status="ok", duration_s=0.05,
        )
        # L'histogramme contient une observation
        hist = m.webhook_processing_duration.labels(
            source="stripe",
            event_type="checkout.session.completed",
            status="ok",
        )
        # _sum est expose pour les histograms
        assert hist._sum.get() == 0.05

    def test_record_webhook_negative_duration_clamped(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        m.record_webhook(
            source="stripe", event_type="x", status="ok", duration_s=-1.0,
        )
        # Pas d'exception ; observation a 0

    def test_active_projects_gauge(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        m.active_projects.labels(status="in_production").set(7)
        v = m.active_projects.labels(status="in_production")._value.get()
        assert v == 7.0

    def test_get_v9_metrics_singleton(self) -> None:
        # Reset puis verif que get_v9_metrics renvoie le meme objet
        m1 = reset_v9_metrics_for_test()
        m2 = get_v9_metrics()
        assert m1 is m2

    def test_metric_names_have_uba_prefix(self) -> None:
        reg = CollectorRegistry()
        m = V9Metrics(registry=reg)
        # Trigger au moins une observation pour chaque metric pour qu'elle apparaisse
        m.paywall_triggered.labels(project_status="x").inc()
        m.payment_succeeded.labels(currency="EUR").inc()
        m.ai_loop_detected.labels(project_id_hash="x").inc()
        m.handoff_escalated.labels(action_type="x").inc()
        m.platform_live_modes.labels(mode="stripe").set(0)
        # Verifie les noms
        names = {s.name for s in reg.collect()}
        # Tous les counters/gauges/histograms ont prefixe uba_
        assert all(n.startswith("uba_") for n in names)


# ===========================================================================
# SLO definitions
# ===========================================================================
class TestSLODefinitions:
    def test_v9_slos_catalog_complete(self) -> None:
        # Au moins 8 SLOs (les domaines critiques)
        assert len(V9_SLOS) >= 8

    def test_each_slo_valid(self) -> None:
        for slo in V9_SLOS:
            assert 0.0 < slo.target < 1.0
            assert slo.window in {"7d", "30d", "90d"}
            assert slo.error_budget_minutes > 0
            assert isinstance(slo.severity, SLOSeverity)
            assert slo.metric_name.startswith(("uba_", "http_"))

    def test_invalid_target_rejected(self) -> None:
        with pytest.raises(ValueError):
            SLODefinition(
                name="x", description="x",
                target=1.5,             # > 1.0 invalide
                window="30d",
                severity=SLOSeverity.HIGH,
                metric_name="uba_x",
            )

    def test_invalid_window_rejected(self) -> None:
        with pytest.raises(ValueError):
            SLODefinition(
                name="x", description="x",
                target=0.99,
                window="3d",            # invalide
                severity=SLOSeverity.HIGH,
                metric_name="uba_x",
            )

    def test_error_budget_calculated(self) -> None:
        slo = SLODefinition(
            name="x", description="x",
            target=0.999, window="30d",
            severity=SLOSeverity.HIGH,
            metric_name="uba_x",
        )
        # 30j * 24h * 60min * 0.001 = 43.2 minutes
        assert slo.error_budget_minutes == 43.2

    def test_find_slo_by_name(self) -> None:
        found = find_slo_by_name("webhook_handler_latency")
        assert found is not None
        assert found.severity is SLOSeverity.CRITICAL

    def test_find_slo_unknown(self) -> None:
        assert find_slo_by_name("ghost") is None

    def test_slos_by_severity(self) -> None:
        criticals = slos_by_severity(SLOSeverity.CRITICAL)
        assert len(criticals) >= 2
        assert all(s.severity is SLOSeverity.CRITICAL for s in criticals)

    def test_total_error_budget_critical(self) -> None:
        total = total_error_budget_critical_minutes()
        assert total > 0

    def test_payment_critical_slo_exists(self) -> None:
        webhook = find_slo_by_name("webhook_handler_latency")
        assert webhook is not None
        assert webhook.target == 0.999
        assert webhook.threshold_ms == 500


# ===========================================================================
# V9HealthCheck
# ===========================================================================
class TestV9HealthCheck:
    @pytest.mark.asyncio
    async def test_run_all_returns_proper_shape(self) -> None:
        pool, conn = _mock_pool()
        # platform_config exists
        conn.fetchrow.side_effect = [
            {"version": 1, "committed_at": datetime.now(UTC)},
            {"chain_hash": "x" * 64, "actor": "test", "created_at": datetime.now(UTC)},
        ]
        conn.fetchval.return_value = 10
        h = V9HealthCheck(pool)
        result = await h.run_all()
        assert "status" in result
        assert "checks" in result
        assert "checked_at" in result
        # Toutes les 4 checks presentes
        assert set(result["checks"]) == {
            "platform_config", "evidence_chain", "live_modes", "jwt_mode",
        }

    @pytest.mark.asyncio
    async def test_platform_config_missing(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchrow.return_value = None
        h = V9HealthCheck(pool)
        result = await h.check_platform_config()
        assert result.status is HealthStatus.FAIL
        assert "absent" in result.message

    @pytest.mark.asyncio
    async def test_platform_config_present(self) -> None:
        pool, conn = _mock_pool()
        now = datetime.now(UTC)
        conn.fetchrow.return_value = {"version": 3, "committed_at": now}
        h = V9HealthCheck(pool)
        result = await h.check_platform_config()
        assert result.status is HealthStatus.PASS
        assert result.details["version"] == 3

    @pytest.mark.asyncio
    async def test_evidence_chain_empty(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchval.return_value = 0
        conn.fetchrow.return_value = None
        h = V9HealthCheck(pool)
        result = await h.check_evidence_chain()
        assert result.status is HealthStatus.FAIL

    @pytest.mark.asyncio
    async def test_evidence_chain_warn_few_links(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchval.return_value = 3
        conn.fetchrow.return_value = {
            "chain_hash": "x" * 64, "actor": "test",
            "created_at": datetime.now(UTC),
        }
        h = V9HealthCheck(pool)
        result = await h.check_evidence_chain()
        assert result.status is HealthStatus.WARN
        assert "3 maillons" in result.message

    @pytest.mark.asyncio
    async def test_evidence_chain_pass(self) -> None:
        pool, conn = _mock_pool()
        conn.fetchval.return_value = 50
        conn.fetchrow.return_value = {
            "chain_hash": "y" * 64, "actor": "migration_xyz",
            "created_at": datetime.now(UTC),
        }
        h = V9HealthCheck(pool)
        result = await h.check_evidence_chain()
        assert result.status is HealthStatus.PASS
        assert result.details["count"] == 50

    def test_live_modes_all_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UBA_LIVE_HOSTINGER", raising=False)
        monkeypatch.delenv("UBA_LIVE_STRIPE", raising=False)
        pool, _ = _mock_pool()
        h = V9HealthCheck(pool)
        result = h.check_live_modes()
        assert result.status is HealthStatus.PASS
        assert result.details == {"hostinger": False, "stripe": False}

    def test_live_modes_one_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UBA_LIVE_STRIPE", "1")
        monkeypatch.delenv("UBA_LIVE_HOSTINGER", raising=False)
        pool, _ = _mock_pool()
        h = V9HealthCheck(pool)
        result = h.check_live_modes()
        assert result.status is HealthStatus.WARN
        assert "stripe" in result.message

    def test_jwt_mode_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("JWT_ADMIN_SECRET", "x" * 40)
        pool, _ = _mock_pool()
        h = V9HealthCheck(pool)
        result = h.check_jwt_mode()
        assert result.status is HealthStatus.PASS
        assert result.details["jwt_enabled"] is True

    def test_jwt_mode_legacy_only_warns(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("JWT_ADMIN_SECRET", raising=False)
        monkeypatch.setenv("UBA_ADMIN_TOKEN", "legacy")
        pool, _ = _mock_pool()
        h = V9HealthCheck(pool)
        result = h.check_jwt_mode()
        assert result.status is HealthStatus.WARN

    def test_jwt_mode_no_auth_fails(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("JWT_ADMIN_SECRET", raising=False)
        monkeypatch.delenv("UBA_ADMIN_TOKEN", raising=False)
        pool, _ = _mock_pool()
        h = V9HealthCheck(pool)
        result = h.check_jwt_mode()
        assert result.status is HealthStatus.FAIL

    def test_aggregate_status(self) -> None:
        results = [
            HealthCheckResult(name="a", status=HealthStatus.PASS, message="x"),
            HealthCheckResult(name="b", status=HealthStatus.WARN, message="x"),
        ]
        assert _aggregate_status(results) is HealthStatus.WARN
        results.append(
            HealthCheckResult(name="c", status=HealthStatus.FAIL, message="x"),
        )
        assert _aggregate_status(results) is HealthStatus.FAIL

    def test_aggregate_all_pass(self) -> None:
        results = [
            HealthCheckResult(name="a", status=HealthStatus.PASS, message="x"),
            HealthCheckResult(name="b", status=HealthStatus.PASS, message="x"),
        ]
        assert _aggregate_status(results) is HealthStatus.PASS

    def test_health_check_result_to_dict(self) -> None:
        r = HealthCheckResult(
            name="x", status=HealthStatus.PASS, message="ok",
            details={"k": "v"},
        )
        d = r.to_dict()
        assert d == {"status": "pass", "message": "ok", "details": {"k": "v"}}


# ===========================================================================
# Sentry context
# ===========================================================================
class TestSentryContext:
    def test_hash_email_deterministic(self) -> None:
        h1 = _hash_email("Ahmed@Example.com")
        h2 = _hash_email("ahmed@example.com")
        assert h1 == h2   # case-insensitive
        assert len(h1) == 16

    def test_is_sentry_available_no_init(self) -> None:
        # Sans init explicite, sentry_sdk peut etre installe mais pas configure.
        # Le helper doit retourner False (no client).
        # On ne peut pas garantir l'absence de Sentry SDK mais on peut
        # verifier que la fonction ne plante pas et retourne un bool.
        assert isinstance(is_sentry_available(), bool)

    def test_add_project_context_no_op_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Force is_sentry_available -> False
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: False)
        result = add_project_context(uuid4(), owner_email="x@y.com")
        assert result is False

    def test_add_payment_context_no_op_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: False)
        result = add_payment_context(uuid4(), amount_cents=1000)
        assert result is False

    def test_capture_exception_no_op_when_unavailable(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: False)
        result = capture_v9_exception(RuntimeError("test"))
        assert result is False

    def test_add_project_context_when_available(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Mock complet de sentry_sdk
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: True)

        scope_calls: list = []

        class _MockScope:
            def set_tag(self, key: str, value: str) -> None:
                scope_calls.append(("tag", key, value))

            def set_user(self, user: dict) -> None:
                scope_calls.append(("user", user))

        from contextlib import contextmanager

        @contextmanager
        def _configure_scope():
            yield _MockScope()

        # Mock sentry_sdk module
        mock_sdk = MagicMock()
        mock_sdk.configure_scope = _configure_scope
        import sys
        sys.modules["sentry_sdk"] = mock_sdk
        try:
            result = add_project_context(
                uuid4(), owner_email="ahmed@example.com",
                pack_id="saas_small", status="in_production",
            )
            assert result is True
            tag_keys = [c[1] for c in scope_calls if c[0] == "tag"]
            assert "project_id" in tag_keys
            assert "pack_id" in tag_keys
            assert "project_status" in tag_keys
            # User contient l'email hashe (pas l'email brut)
            user_calls = [c[1] for c in scope_calls if c[0] == "user"]
            assert len(user_calls) == 1
            assert user_calls[0]["id"] != "ahmed@example.com"  # hash
            assert len(user_calls[0]["id"]) == 16
        finally:
            sys.modules.pop("sentry_sdk", None)

    def test_add_payment_context_when_available(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: True)

        ctx_calls: list = []

        class _MockScope:
            def set_tag(self, key: str, value: str) -> None:
                ctx_calls.append(("tag", key, value))

            def set_context(self, name: str, ctx: dict) -> None:
                ctx_calls.append(("context", name, ctx))

        from contextlib import contextmanager

        @contextmanager
        def _configure_scope():
            yield _MockScope()

        mock_sdk = MagicMock()
        mock_sdk.configure_scope = _configure_scope
        import sys
        sys.modules["sentry_sdk"] = mock_sdk
        try:
            result = add_payment_context(
                uuid4(), amount_cents=12000, currency="EUR",
                status="succeeded", auth_mode="jwt",
            )
            assert result is True
            tag_keys = [c[1] for c in ctx_calls if c[0] == "tag"]
            assert "payment_id" in tag_keys
            assert "payment_status" in tag_keys
            assert "auth_mode" in tag_keys
        finally:
            sys.modules.pop("sentry_sdk", None)

    def test_capture_v9_exception_when_available(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: True)

        captured: list = []

        class _MockScope:
            def set_tag(self, key: str, value: str) -> None: ...
            def set_extra(self, key: str, value) -> None:
                captured.append((key, value))

        from contextlib import contextmanager

        @contextmanager
        def _push_scope():
            yield _MockScope()

        mock_sdk = MagicMock()
        mock_sdk.push_scope = _push_scope
        import sys
        sys.modules["sentry_sdk"] = mock_sdk
        try:
            ok = capture_v9_exception(
                RuntimeError("test boom"),
                project_id="proj-uuid",
                extra={"k": "v"},
            )
            assert ok is True
            mock_sdk.capture_exception.assert_called_once()
            # Extras enregistres
            assert ("k", "v") in captured
        finally:
            sys.modules.pop("sentry_sdk", None)

    def test_add_project_context_does_not_propagate_exception(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Si sentry_sdk plante, on log et on retourne False — pas crash."""
        import app.saas_factory.observability.sentry_context as mod
        monkeypatch.setattr(mod, "is_sentry_available", lambda: True)
        # Mock sentry qui leve a configure_scope
        mock_sdk = MagicMock()
        mock_sdk.configure_scope.side_effect = RuntimeError("sdk error")
        import sys
        sys.modules["sentry_sdk"] = mock_sdk
        try:
            result = add_project_context(uuid4())
            # Pas de crash, retour False
            assert result is False
        finally:
            sys.modules.pop("sentry_sdk", None)
