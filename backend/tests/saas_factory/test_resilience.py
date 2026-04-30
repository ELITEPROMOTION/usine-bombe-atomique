"""Tests Phase 9L — resilience patterns (CB / timeouts / kill switch / policies)."""
from __future__ import annotations

import asyncio

import pytest

from app.saas_factory.resilience import (
    RESILIENCE_POLICIES,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    KillSwitchRegistry,
    ResiliencePolicy,
    ResilienceTimeoutError,
    TimeoutPolicy,
    get_kill_switches,
    get_policy,
    with_timeout,
)
from app.saas_factory.resilience.kill_switch import KillSwitchActiveError


# ===========================================================================
# CircuitBreakerConfig validation
# ===========================================================================
class TestCircuitBreakerConfig:
    def test_valid_config(self):
        cfg = CircuitBreakerConfig(name="test")
        assert cfg.name == "test"
        assert cfg.failure_threshold == 5

    def test_invalid_failure_threshold(self):
        with pytest.raises(ValueError, match="failure_threshold"):
            CircuitBreakerConfig(name="test", failure_threshold=0)

    def test_invalid_success_threshold(self):
        with pytest.raises(ValueError, match="success_threshold"):
            CircuitBreakerConfig(name="test", success_threshold=0)

    def test_invalid_cooldown(self):
        with pytest.raises(ValueError, match="cooldown_seconds"):
            CircuitBreakerConfig(name="test", cooldown_seconds=-1)

    def test_invalid_half_open_max(self):
        with pytest.raises(ValueError, match="half_open_max_calls"):
            CircuitBreakerConfig(name="test", half_open_max_calls=0)


# ===========================================================================
# CircuitBreaker state machine
# ===========================================================================
class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test"))
        assert cb.state is CircuitState.CLOSED
        assert cb.stats.total_calls == 0

    @pytest.mark.asyncio
    async def test_call_success_pass_through(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test"))

        async def ok():
            return 42

        assert await cb.call(ok) == 42
        assert cb.stats.total_successes == 1
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failures_below_threshold_stay_closed(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(name="test", failure_threshold=3),
        )

        async def fail():
            raise ValueError("nope")

        for _ in range(2):
            with pytest.raises(ValueError, match="nope"):
                await cb.call(fail)
        assert cb.state is CircuitState.CLOSED
        assert cb.stats.consecutive_failures == 2

    @pytest.mark.asyncio
    async def test_failures_at_threshold_opens(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(name="test", failure_threshold=2),
        )

        async def fail():
            raise ValueError("boom")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail)
        assert cb.state is CircuitState.OPEN
        assert cb.stats.state_transitions == 1
        assert "boom" in (cb.stats.last_failure_message or "")

    @pytest.mark.asyncio
    async def test_open_rejects_calls(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                name="test", failure_threshold=1, cooldown_seconds=10,
            ),
        )

        async def fail():
            raise ValueError("x")

        with pytest.raises(ValueError):
            await cb.call(fail)
        # second call : reject
        with pytest.raises(CircuitBreakerOpenError, match="OPEN"):
            await cb.call(fail)
        assert cb.stats.total_rejections == 1

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_cooldown(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                name="test", failure_threshold=1, cooldown_seconds=0.05,
            ),
        )

        async def fail():
            raise ValueError("x")

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state is CircuitState.OPEN
        await asyncio.sleep(0.1)

        async def ok():
            return "ok"

        # appel apres cooldown : on passe en HALF_OPEN puis CLOSED
        assert await cb.call(ok) == "ok"
        # success_threshold default = 2, donc encore HALF_OPEN
        assert cb.state is CircuitState.HALF_OPEN
        assert await cb.call(ok) == "ok"
        assert cb.state is CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_returns_to_open(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                name="test", failure_threshold=1, cooldown_seconds=0.05,
            ),
        )

        async def fail():
            raise ValueError("x")

        with pytest.raises(ValueError):
            await cb.call(fail)
        await asyncio.sleep(0.1)

        # echec en HALF_OPEN -> retour OPEN
        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state is CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_max_calls_limit(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                name="test",
                failure_threshold=1,
                cooldown_seconds=0.05,
                half_open_max_calls=1,
                success_threshold=10,         # haut pour rester en HALF_OPEN
            ),
        )

        async def fail():
            raise ValueError("x")

        with pytest.raises(ValueError):
            await cb.call(fail)
        await asyncio.sleep(0.1)

        # premiere call HALF_OPEN consomme le slot
        async def slow_ok():
            await asyncio.sleep(0.1)
            return "ok"

        task1 = asyncio.create_task(cb.call(slow_ok))
        # laisser le temps au lock d'etre acquired
        await asyncio.sleep(0.01)
        # seconde call doit etre rejetee (slot pris)
        with pytest.raises(CircuitBreakerOpenError, match="half-open"):
            await cb.call(slow_ok)
        await task1

    @pytest.mark.asyncio
    async def test_unexpected_exception_does_not_count(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(
                name="test",
                failure_threshold=2,
                expected_exceptions=(ValueError,),
            ),
        )

        async def raise_typeerror():
            raise TypeError("not counted")

        for _ in range(5):
            with pytest.raises(TypeError):
                await cb.call(raise_typeerror)
        assert cb.state is CircuitState.CLOSED
        assert cb.stats.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_success_resets_consecutive_failures(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(name="test", failure_threshold=3),
        )

        async def fail():
            raise ValueError("x")

        async def ok():
            return 1

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.stats.consecutive_failures == 1
        await cb.call(ok)
        assert cb.stats.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_reset_force_closed(self):
        cb = CircuitBreaker(
            CircuitBreakerConfig(name="test", failure_threshold=1),
        )

        async def fail():
            raise ValueError("x")

        with pytest.raises(ValueError):
            await cb.call(fail)
        assert cb.state is CircuitState.OPEN
        await cb.reset()
        assert cb.state is CircuitState.CLOSED
        assert cb.stats.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_call_propagates_arguments(self):
        cb = CircuitBreaker(CircuitBreakerConfig(name="test"))

        async def add(a, b, *, c=0):
            return a + b + c

        assert await cb.call(add, 1, 2, c=3) == 6


# ===========================================================================
# TimeoutPolicy
# ===========================================================================
class TestTimeoutPolicy:
    def test_valid_policy(self):
        p = TimeoutPolicy(name="test", total_seconds=10.0)
        assert p.total_seconds == 10.0
        assert p.connect_seconds == 5.0

    def test_total_must_be_positive(self):
        with pytest.raises(ValueError):
            TimeoutPolicy(name="test", total_seconds=0)

    def test_connect_negative_invalid(self):
        with pytest.raises(ValueError):
            TimeoutPolicy(name="test", total_seconds=5, connect_seconds=-1)

    def test_connect_cannot_exceed_total(self):
        with pytest.raises(ValueError, match="cannot exceed"):
            TimeoutPolicy(name="test", total_seconds=5, connect_seconds=10)

    @pytest.mark.asyncio
    async def test_with_timeout_completes_under_budget(self):
        async def fast():
            await asyncio.sleep(0.01)
            return "done"

        result = await with_timeout(
            fast(),
            TimeoutPolicy(
                name="test", total_seconds=10.0, connect_seconds=1.0,
            ),
        )
        assert result == "done"

    @pytest.mark.asyncio
    async def test_with_timeout_raises_on_overrun(self):
        async def slow():
            await asyncio.sleep(0.5)
            return "never"

        with pytest.raises(ResilienceTimeoutError, match="test"):
            await with_timeout(
                slow(),
                TimeoutPolicy(
                    name="test",
                    total_seconds=0.05,
                    connect_seconds=0.0,
                ),
            )


# ===========================================================================
# KillSwitchRegistry
# ===========================================================================
class TestKillSwitchRegistry:
    def test_kill_switch_off_by_default(self):
        reg = KillSwitchRegistry(known=("stripe",), env={})
        assert reg.is_active("stripe") is False
        reg.ensure_alive("stripe")  # no raise

    def test_kill_switch_on_when_set(self):
        reg = KillSwitchRegistry(
            known=("stripe",), env={"UBA_KILL_STRIPE": "1"},
        )
        assert reg.is_active("stripe") is True
        with pytest.raises(KillSwitchActiveError, match="STRIPE"):
            reg.ensure_alive("stripe")

    def test_only_exact_one_activates(self):
        reg = KillSwitchRegistry(
            known=("stripe",), env={"UBA_KILL_STRIPE": "true"},
        )
        # seul "1" est active — "true" -> off
        assert reg.is_active("stripe") is False

    def test_snapshot_returns_all_known(self):
        reg = KillSwitchRegistry(
            known=("stripe", "hostinger"),
            env={"UBA_KILL_STRIPE": "1"},
        )
        snap = reg.snapshot()
        assert snap == {"stripe": True, "hostinger": False}

    def test_singleton_returns_same_instance(self):
        a = get_kill_switches()
        b = get_kill_switches()
        assert a is b

    def test_dependency_case_insensitive(self):
        reg = KillSwitchRegistry(
            known=("stripe",), env={"UBA_KILL_STRIPE": "1"},
        )
        assert reg.is_active("STRIPE") is True
        assert reg.is_active("Stripe") is True


# ===========================================================================
# Policies catalog
# ===========================================================================
class TestPolicies:
    def test_known_dependencies(self):
        for dep in (
            "stripe", "hostinger", "anthropic",
            "openai", "resend", "postgres",
        ):
            policy = get_policy(dep)
            assert isinstance(policy, ResiliencePolicy)
            assert policy.dependency == dep

    def test_unknown_dependency_raises(self):
        with pytest.raises(KeyError, match="unknown dependency"):
            get_policy("notfound")

    def test_lookup_case_insensitive(self):
        assert get_policy("STRIPE").dependency == "stripe"

    def test_each_policy_has_consistent_names(self):
        for dep, policy in RESILIENCE_POLICIES.items():
            assert policy.dependency == dep
            assert policy.circuit.name == dep
            assert policy.timeout.name == dep

    def test_postgres_has_short_timeout(self):
        # DB doit avoir un budget court
        assert get_policy("postgres").timeout.total_seconds <= 10

    def test_anthropic_has_long_timeout(self):
        # IA peut prendre >30s
        assert get_policy("anthropic").timeout.total_seconds >= 30
