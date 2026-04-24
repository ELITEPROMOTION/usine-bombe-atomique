"""Tests circuit breakers V5.7."""
from __future__ import annotations

import asyncio

import pytest

from app.resilience import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitBreakerRegistry,
    with_circuit_breaker,
)

pytestmark = pytest.mark.asyncio


# ---------- CircuitBreaker core ----------

async def test_breaker_starts_closed() -> None:
    cb = CircuitBreaker(name="test", fail_threshold=3)
    assert cb.state is BreakerState.CLOSED


async def test_breaker_successful_call() -> None:
    cb = CircuitBreaker(name="test", fail_threshold=3)

    async def ok():
        return 42

    assert await cb.call(ok) == 42
    assert cb.metrics.successful_calls == 1
    assert cb.metrics.failed_calls == 0


async def test_breaker_opens_after_threshold() -> None:
    cb = CircuitBreaker(name="test", fail_threshold=3, timeout_s=1.0)

    async def boom():
        raise RuntimeError("fail")

    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(boom)
    assert cb.state is BreakerState.OPEN
    assert cb.metrics.failed_calls == 3


async def test_breaker_open_rejects_calls() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1, timeout_s=1.0)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert cb.state is BreakerState.OPEN

    # subsequent call rejected
    with pytest.raises(CircuitBreakerOpenError):
        await cb.call(boom)
    assert cb.metrics.rejected_calls == 1


async def test_breaker_half_open_after_recovery() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1, timeout_s=1.0,
                         recovery_s=0.1)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert cb.state is BreakerState.OPEN
    await asyncio.sleep(0.2)
    # Accessing state triggers transition
    assert cb.state is BreakerState.HALF_OPEN


async def test_breaker_half_open_success_closes() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1, recovery_s=0.1)

    async def boom():
        raise RuntimeError("x")

    async def ok():
        return 1

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    await asyncio.sleep(0.2)
    assert cb.state is BreakerState.HALF_OPEN
    assert await cb.call(ok) == 1
    assert cb.state is BreakerState.CLOSED


async def test_breaker_half_open_failure_reopens() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1, recovery_s=0.1)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    await asyncio.sleep(0.2)
    _ = cb.state  # trigger transition -> HALF_OPEN
    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert cb.state is BreakerState.OPEN


async def test_breaker_timeout() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1, timeout_s=0.05)

    async def slow():
        await asyncio.sleep(1)
        return 1

    with pytest.raises(asyncio.TimeoutError):
        await cb.call(slow)
    assert cb.metrics.failed_calls == 1


async def test_breaker_with_fallback() -> None:
    async def fallback_fn(*args, **kwargs):
        return {"fallback": True}

    cb = CircuitBreaker(name="t", fail_threshold=1, fallback=fallback_fn)

    async def boom():
        raise RuntimeError("x")

    # premier appel -> fail + OPEN (fallback NOT called on first fail)
    result = await cb.call(boom)
    assert result == {"fallback": True}  # fallback used


async def test_breaker_reset() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert cb.state is BreakerState.OPEN
    cb.reset()
    assert cb.state is BreakerState.CLOSED


async def test_breaker_to_dict() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=3)
    d = cb.to_dict()
    assert d["name"] == "t"
    assert d["state"] == "closed"
    assert "metrics" in d


async def test_breaker_state_changes_recorded() -> None:
    cb = CircuitBreaker(name="t", fail_threshold=1)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert len(cb.metrics.state_changes) >= 1


# ---------- Registry ----------

def test_registry_singleton() -> None:
    r1 = CircuitBreakerRegistry.instance()
    r2 = CircuitBreakerRegistry.instance()
    assert r1 is r2


def test_registry_has_6_default_breakers() -> None:
    r = CircuitBreakerRegistry.instance()
    breakers = r.list_all()
    names = {b["name"] for b in breakers}
    assert {"claude_api", "postgres", "redis", "sonarqube", "vault",
             "external_webhook"} == names


def test_registry_get_unknown_raises() -> None:
    r = CircuitBreakerRegistry.instance()
    with pytest.raises(KeyError):
        r.get("nonexistent")


def test_registry_reset_all() -> None:
    r = CircuitBreakerRegistry.instance()
    # Force-open postgres breaker
    pg = r.get("postgres")
    pg._state = BreakerState.OPEN  # type: ignore[misc]
    r.reset_all()
    assert pg.state is BreakerState.CLOSED


# ---------- Decorator ----------

async def test_decorator_routes_via_breaker() -> None:
    @with_circuit_breaker("claude_api")
    async def fn(x: int) -> int:
        return x * 2

    assert await fn(5) == 10


def test_decorator_sets_attribute() -> None:
    @with_circuit_breaker("redis")
    async def fn() -> int:
        return 1

    assert fn.__circuit_breaker__ == "redis"  # type: ignore[attr-defined]


# ---------- Parametres ----------

def test_default_breakers_thresholds() -> None:
    r = CircuitBreakerRegistry.instance()
    assert r.get("claude_api").fail_threshold == 5
    assert r.get("postgres").fail_threshold == 10
    assert r.get("redis").fail_threshold == 3
    assert r.get("sonarqube").fail_threshold == 3
    assert r.get("vault").fail_threshold == 5
    assert r.get("external_webhook").fail_threshold == 3


def test_fallbacks_configured() -> None:
    r = CircuitBreakerRegistry.instance()
    # Breakers avec fallback
    assert r.get("claude_api").fallback is not None
    assert r.get("sonarqube").fallback is not None
    assert r.get("external_webhook").fallback is not None
    # Breakers sans fallback (hard fail)
    assert r.get("postgres").fallback is None
    assert r.get("redis").fallback is None
