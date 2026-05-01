"""Tests Phase 9L — chaos engineering (scenarios + injector + runner)."""
from __future__ import annotations

import asyncio

import pytest

from app.saas_factory.chaos import (
    CHAOS_SCENARIOS,
    ChaosDisabledError,
    ChaosInjector,
    ChaosScenario,
    FailureMode,
    InjectionEvent,
    get_scenario,
    run_scenario,
)


# ===========================================================================
# ChaosScenario validation
# ===========================================================================
class TestChaosScenarioValidation:
    def test_valid_scenario(self):
        s = ChaosScenario(
            name="x", description="test",
            failure_modes=(FailureMode.ERROR,),
        )
        assert s.failure_probability == 1.0

    def test_invalid_probability_negative(self):
        with pytest.raises(ValueError, match="probability"):
            ChaosScenario(
                name="x", description="t",
                failure_modes=(FailureMode.ERROR,),
                failure_probability=-0.1,
            )

    def test_invalid_probability_over_one(self):
        with pytest.raises(ValueError, match="probability"):
            ChaosScenario(
                name="x", description="t",
                failure_modes=(FailureMode.ERROR,),
                failure_probability=1.5,
            )

    def test_invalid_delay_negative(self):
        with pytest.raises(ValueError, match="delay_seconds"):
            ChaosScenario(
                name="x", description="t",
                failure_modes=(FailureMode.ERROR,),
                delay_seconds=-1,
            )

    def test_empty_failure_modes_invalid(self):
        with pytest.raises(ValueError, match="failure_mode"):
            ChaosScenario(
                name="x", description="t", failure_modes=(),
            )


# ===========================================================================
# Catalog
# ===========================================================================
class TestChaosCatalog:
    def test_catalog_has_all_expected(self):
        expected = {
            "stripe_down", "stripe_intermittent",
            "hostinger_dns_slow", "anthropic_rate_limit",
            "anthropic_auth_failure", "db_pool_exhausted",
            "partial_failure", "resend_silent_drop",
        }
        assert set(CHAOS_SCENARIOS.keys()) == expected

    def test_get_scenario_known(self):
        assert get_scenario("stripe_down").name == "stripe_down"

    def test_get_scenario_unknown(self):
        with pytest.raises(KeyError, match="unknown scenario"):
            get_scenario("does_not_exist")


# ===========================================================================
# ChaosInjector — gate UBA_CHAOS_ENABLED
# ===========================================================================
class TestChaosInjectorGate:
    def test_gate_blocks_without_enabled(self, monkeypatch):
        monkeypatch.delenv("UBA_CHAOS_ENABLED", raising=False)
        with pytest.raises(ChaosDisabledError, match="UBA_CHAOS_ENABLED"):
            ChaosInjector(get_scenario("stripe_down"))

    def test_explicit_enabled_bypasses_env(self, monkeypatch):
        monkeypatch.delenv("UBA_CHAOS_ENABLED", raising=False)
        # ne doit pas lever
        ChaosInjector(get_scenario("stripe_down"), enabled=True)

    def test_env_enables(self, monkeypatch):
        monkeypatch.setenv("UBA_CHAOS_ENABLED", "1")
        # ne doit pas lever
        ChaosInjector(get_scenario("stripe_down"))


# ===========================================================================
# ChaosInjector — invoke
# ===========================================================================
class TestChaosInjectorInvoke:
    @pytest.mark.asyncio
    async def test_zero_probability_pass_through(self):
        scenario = ChaosScenario(
            name="never", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=0.0,
            seed=1,
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def add(a, b):
            return a + b

        assert await injector.invoke(add, 2, 3) == 5
        assert injector.events[-1].failure_mode is None

    @pytest.mark.asyncio
    async def test_full_probability_error(self):
        scenario = ChaosScenario(
            name="always_err", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=1.0,
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return "real"

        with pytest.raises(RuntimeError, match=r"\[chaos\]"):
            await injector.invoke(f)
        assert injector.events[-1].failure_mode is FailureMode.ERROR

    @pytest.mark.asyncio
    async def test_timeout_mode(self):
        scenario = ChaosScenario(
            name="t", description="t",
            failure_modes=(FailureMode.TIMEOUT,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return 1

        with pytest.raises(asyncio.TimeoutError):
            await injector.invoke(f)

    @pytest.mark.asyncio
    async def test_connection_reset_mode(self):
        scenario = ChaosScenario(
            name="x", description="t",
            failure_modes=(FailureMode.CONNECTION_RESET,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return 1

        with pytest.raises(ConnectionResetError):
            await injector.invoke(f)

    @pytest.mark.asyncio
    async def test_rate_limited_mode(self):
        scenario = ChaosScenario(
            name="x", description="t",
            failure_modes=(FailureMode.RATE_LIMITED,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return 1

        with pytest.raises(RuntimeError) as excinfo:
            await injector.invoke(f)
        assert getattr(excinfo.value, "status_code", None) == 429

    @pytest.mark.asyncio
    async def test_auth_failure_mode(self):
        scenario = ChaosScenario(
            name="x", description="t",
            failure_modes=(FailureMode.AUTH_FAILURE,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return 1

        with pytest.raises(RuntimeError) as excinfo:
            await injector.invoke(f)
        assert getattr(excinfo.value, "status_code", None) == 401

    @pytest.mark.asyncio
    async def test_slow_response_delays_then_passes(self):
        scenario = ChaosScenario(
            name="slow", description="t",
            failure_modes=(FailureMode.SLOW_RESPONSE,),
            delay_seconds=0.05,
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return "ok"

        loop = asyncio.get_event_loop()
        t0 = loop.time()
        result = await injector.invoke(f)
        elapsed = loop.time() - t0
        assert result == "ok"
        assert elapsed >= 0.04

    @pytest.mark.asyncio
    async def test_partial_data_truncates_dict(self):
        scenario = ChaosScenario(
            name="trunc", description="t",
            failure_modes=(FailureMode.PARTIAL_DATA,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return {"a": 1, "b": 2, "c": 3, "d": 4}

        result = await injector.invoke(f)
        assert isinstance(result, dict)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_partial_data_truncates_list(self):
        scenario = ChaosScenario(
            name="trunc", description="t",
            failure_modes=(FailureMode.PARTIAL_DATA,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return [1, 2, 3, 4]

        result = await injector.invoke(f)
        assert result == [1, 2]

    @pytest.mark.asyncio
    async def test_partial_data_unknown_type_returns_none(self):
        scenario = ChaosScenario(
            name="trunc", description="t",
            failure_modes=(FailureMode.PARTIAL_DATA,),
        )
        injector = ChaosInjector(scenario, enabled=True)

        async def f():
            return 42

        assert await injector.invoke(f) is None

    @pytest.mark.asyncio
    async def test_seeded_scenario_is_deterministic(self):
        scenario = ChaosScenario(
            name="det", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=0.5,
            seed=42,
        )
        # Deux runs avec meme seed -> meme suite d'evenements
        out1: list[bool] = []
        out2: list[bool] = []
        for out in (out1, out2):
            inj = ChaosInjector(scenario, enabled=True)
            for _ in range(20):
                try:
                    await inj.invoke(_async_one)
                    out.append(False)
                except RuntimeError:
                    out.append(True)
        assert out1 == out2

    @pytest.mark.asyncio
    async def test_injection_event_recorded(self):
        scenario = ChaosScenario(
            name="x", description="t",
            failure_modes=(FailureMode.ERROR,),
        )
        injector = ChaosInjector(scenario, enabled=True)
        with pytest.raises(RuntimeError):
            await injector.invoke(_async_one)
        ev = injector.events[-1]
        assert isinstance(ev, InjectionEvent)
        assert ev.scenario_name == "x"
        assert ev.failure_mode is FailureMode.ERROR


async def _async_one():
    return 1


# ===========================================================================
# Runner
# ===========================================================================
class TestRunScenario:
    @pytest.mark.asyncio
    async def test_run_iterations_validation(self):
        scenario = get_scenario("partial_failure")
        with pytest.raises(ValueError, match="iterations"):
            await run_scenario(
                scenario, lambda: _async_one(), iterations=0,
            )

    @pytest.mark.asyncio
    async def test_run_collects_outcomes(self):
        # 100% pass-through scenario
        scenario = ChaosScenario(
            name="never", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=0.0,
            seed=0,
        )

        async def action():
            return "ok"

        report = await run_scenario(scenario, action, iterations=5)
        assert report.iterations == 5
        assert report.successes == 5
        assert report.pass_through == 5
        assert report.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_run_collects_failures(self):
        scenario = ChaosScenario(
            name="always", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=1.0,
        )

        async def action():
            return 1

        report = await run_scenario(scenario, action, iterations=3)
        assert report.successes == 0
        assert report.failures_by_mode.get(FailureMode.ERROR) == 3
        assert report.raised_exceptions.get("RuntimeError") == 3
        assert report.success_rate == 0.0

    @pytest.mark.asyncio
    async def test_partial_failure_mixed_outcomes(self):
        scenario = ChaosScenario(
            name="mix", description="t",
            failure_modes=(FailureMode.ERROR,),
            failure_probability=0.5,
            seed=42,
        )

        async def action():
            return 1

        report = await run_scenario(scenario, action, iterations=20)
        assert report.iterations == 20
        # avec seed, on a un mix deterministe
        assert 0 < report.successes < 20
        assert report.success_rate < 1.0
