"""Circuit breakers V5.7 (home-grown, pas de dep pybreaker externe).

Architecture :
  CLOSED       -> normal operation, count failures
  OPEN         -> reject all calls immediatement (fallback active)
  HALF_OPEN    -> permet 1 call test, si OK -> CLOSED, si FAIL -> OPEN

6 breakers configures :
  claude_api, postgres, redis, sonarqube, vault, external_webhook

Usage :
    @with_circuit_breaker("claude_api", fallback=_fallback_fn)
    async def call_claude(...): ...

    # Ou direct :
    registry = CircuitBreakerRegistry.instance()
    cb = registry.get("claude_api")
    result = await cb.call(async_fn, *args, **kwargs)
"""
from __future__ import annotations

import asyncio
import functools
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, ClassVar

logger = logging.getLogger("uba.resilience")


class BreakerState(str, Enum):
    CLOSED = "closed"       # Normal - calls go through
    OPEN = "open"           # Broken - calls rejected immediately
    HALF_OPEN = "half_open"  # Testing - allow 1 call to probe


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a call is rejected because the breaker is OPEN."""
    def __init__(self, breaker_name: str, opened_at: float):
        self.breaker_name = breaker_name
        self.opened_at = opened_at
        super().__init__(
            f"Circuit breaker '{breaker_name}' is OPEN "
            f"(since {time.time() - opened_at:.1f}s)"
        )


@dataclass
class CircuitBreakerMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: list[tuple[float, BreakerState, BreakerState]] = field(
        default_factory=list,
    )

    def record_state_change(self, old: BreakerState, new: BreakerState) -> None:
        self.state_changes.append((time.time(), old, new))
        # cap history
        if len(self.state_changes) > 200:
            self.state_changes = self.state_changes[-200:]


@dataclass
class CircuitBreaker:
    """Breaker avec compteur de failures + fenetre de recovery.

    Params :
      name          : identifiant
      fail_threshold: N echecs consecutifs avant OPEN
      timeout_s     : timeout d'un call individuel
      recovery_s    : attente en OPEN avant de passer HALF_OPEN
      fallback      : appelable si breaker OPEN (async ou sync)
    """
    name: str
    fail_threshold: int = 5
    timeout_s: float = 30.0
    recovery_s: float = 30.0
    fallback: Callable[..., Any] | None = None

    # state (mutes via methods guardees par lock)
    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    _opened_at: float = field(default=0.0, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    metrics: CircuitBreakerMetrics = field(
        default_factory=CircuitBreakerMetrics, init=False,
    )

    @property
    def state(self) -> BreakerState:
        with self._lock:
            # Transition OPEN -> HALF_OPEN si recovery_s ecoule
            if (self._state is BreakerState.OPEN and
                time.time() - self._opened_at >= self.recovery_s):
                self._transition(BreakerState.HALF_OPEN)
            return self._state

    def _transition(self, new_state: BreakerState) -> None:
        """Appele SOUS _lock."""
        old = self._state
        if old is new_state:
            return
        self._state = new_state
        self.metrics.record_state_change(old, new_state)
        logger.warning(
            "CircuitBreaker %s : %s -> %s (failures=%d)",
            self.name, old.value, new_state.value, self._consecutive_failures,
        )
        if new_state is BreakerState.OPEN:
            self._opened_at = time.time()
        elif new_state is BreakerState.CLOSED:
            self._consecutive_failures = 0

    async def call(
        self, fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any,
    ) -> Any:
        """Execute fn via le breaker. Raise CircuitBreakerOpenError si OPEN
        et pas de fallback (fallback retourne sa valeur sinon)."""
        with self._lock:
            self.metrics.total_calls += 1
            current_state = self.state

            if current_state is BreakerState.OPEN:
                self.metrics.rejected_calls += 1
                if self.fallback is not None:
                    return await self._run_fallback(*args, **kwargs)
                raise CircuitBreakerOpenError(self.name, self._opened_at)

        try:
            result = await asyncio.wait_for(fn(*args, **kwargs), timeout=self.timeout_s)
        except Exception as exc:
            with self._lock:
                self.metrics.failed_calls += 1
                self._consecutive_failures += 1
                if (current_state is BreakerState.HALF_OPEN or
                    self._consecutive_failures >= self.fail_threshold):
                    self._transition(BreakerState.OPEN)
            if self.fallback is not None:
                logger.warning("breaker %s : fallback triggered (%s)", self.name, exc)
                return await self._run_fallback(*args, **kwargs)
            raise

        # Success : reset counters
        with self._lock:
            self.metrics.successful_calls += 1
            if current_state in (BreakerState.HALF_OPEN, BreakerState.OPEN):
                self._transition(BreakerState.CLOSED)
            elif self._consecutive_failures > 0:
                self._consecutive_failures = 0
        return result

    async def _run_fallback(self, *args: Any, **kwargs: Any) -> Any:
        if self.fallback is None:
            raise RuntimeError("fallback called but None")
        if asyncio.iscoroutinefunction(self.fallback):
            return await self.fallback(*args, **kwargs)
        return self.fallback(*args, **kwargs)

    def reset(self) -> None:
        """Force-reset le breaker a CLOSED (admin action)."""
        with self._lock:
            self._transition(BreakerState.CLOSED)
            self._consecutive_failures = 0

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "state": self.state.value,
                "fail_threshold": self.fail_threshold,
                "timeout_s": self.timeout_s,
                "recovery_s": self.recovery_s,
                "consecutive_failures": self._consecutive_failures,
                "opened_at": self._opened_at or None,
                "metrics": {
                    "total_calls": self.metrics.total_calls,
                    "successful_calls": self.metrics.successful_calls,
                    "failed_calls": self.metrics.failed_calls,
                    "rejected_calls": self.metrics.rejected_calls,
                    "state_changes_count": len(self.metrics.state_changes),
                },
            }


# ============================================================================
# Default fallbacks
# ============================================================================

def _fallback_claude_api(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Template par defaut quand Claude API OPEN."""
    return {
        "fallback": True,
        "content": "[fallback] Claude API unavailable - using template response",
        "model": "fallback-template-v1",
    }


async def _fallback_sonarqube(*args: Any, **kwargs: Any) -> dict[str, Any]:
    logger.warning("sonarqube OPEN - skipping analysis")
    return {"skipped": True, "reason": "sonarqube circuit breaker open"}


async def _fallback_webhook(*args: Any, **kwargs: Any) -> dict[str, Any]:
    logger.warning("webhook OPEN - queued for retry")
    return {"queued": True, "reason": "webhook circuit breaker open"}


# ============================================================================
# CircuitBreakerRegistry - singleton
# ============================================================================

class CircuitBreakerRegistry:
    """Registry singleton des 6 breakers UBA."""

    _instance: ClassVar["CircuitBreakerRegistry | None"] = None
    _instance_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._breakers: dict[str, CircuitBreaker] = {}
        self._register_defaults()

    @classmethod
    def instance(cls) -> "CircuitBreakerRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._instance_lock:
            cls._instance = None

    def _register_defaults(self) -> None:
        defaults = [
            CircuitBreaker(name="claude_api", fail_threshold=5, timeout_s=60.0,
                            recovery_s=30.0, fallback=_fallback_claude_api),
            CircuitBreaker(name="postgres", fail_threshold=10, timeout_s=30.0,
                            recovery_s=10.0),
            CircuitBreaker(name="redis", fail_threshold=3, timeout_s=10.0,
                            recovery_s=5.0),
            CircuitBreaker(name="sonarqube", fail_threshold=3, timeout_s=30.0,
                            recovery_s=60.0, fallback=_fallback_sonarqube),
            CircuitBreaker(name="vault", fail_threshold=5, timeout_s=30.0,
                            recovery_s=30.0),
            CircuitBreaker(name="external_webhook", fail_threshold=3,
                            timeout_s=15.0, recovery_s=30.0,
                            fallback=_fallback_webhook),
        ]
        for cb in defaults:
            self._breakers[cb.name] = cb

    def get(self, name: str) -> CircuitBreaker:
        with self._lock:
            if name not in self._breakers:
                raise KeyError(f"Unknown circuit breaker: {name}")
            return self._breakers[name]

    def register(self, breaker: CircuitBreaker) -> None:
        with self._lock:
            self._breakers[breaker.name] = breaker

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [b.to_dict() for b in self._breakers.values()]

    def reset_all(self) -> None:
        with self._lock:
            for b in self._breakers.values():
                b.reset()


# ============================================================================
# Decorator
# ============================================================================

def with_circuit_breaker(name: str):
    """Decorateur qui route la coroutine via le breaker indique."""
    def decorator(fn: Callable[..., Awaitable[Any]]):
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = CircuitBreakerRegistry.instance().get(name)
            return await cb.call(fn, *args, **kwargs)
        wrapper.__circuit_breaker__ = name  # type: ignore[attr-defined]
        return wrapper
    return decorator
