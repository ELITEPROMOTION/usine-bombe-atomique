"""CircuitBreaker async-safe avec state machine CLOSED -> OPEN -> HALF_OPEN.

Pattern Hystrix-like adapte a asyncio :
- CLOSED : pass-through normal, on incremente les failures sur erreur.
  Apres `failure_threshold` echecs consecutifs, on passe a OPEN.
- OPEN   : tout appel leve immediatement `CircuitBreakerOpenError`. On
  attend `cooldown_seconds` avant de tenter un essai en HALF_OPEN.
- HALF_OPEN : un nombre limite (`half_open_max_calls`) de calls passent
  pour tester si le service est revenu. `success_threshold` succes
  consecutifs en HALF_OPEN -> retour CLOSED. Le moindre echec -> OPEN.

Cf. ADR-29.
"""
from __future__ import annotations

import asyncio
import enum
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(str, enum.Enum):
    CLOSED = "closed"        # nominal
    OPEN = "open"            # fail-fast active
    HALF_OPEN = "half_open"  # test de re-ouverture


class CircuitBreakerOpenError(RuntimeError):
    """Leve quand un appel est rejete par un CB en etat OPEN."""

    def __init__(self, name: str, last_failure: str | None = None) -> None:
        msg = f"circuit '{name}' OPEN"
        if last_failure:
            msg += f" (last failure: {last_failure})"
        super().__init__(msg)
        self.name = name
        self.last_failure = last_failure


@dataclass(frozen=True)
class CircuitBreakerConfig:
    """Configuration immutable d'un CircuitBreaker."""

    name: str                                   # identifiant (e.g. 'stripe')
    failure_threshold: int = 5                  # echecs consecutifs avant OPEN
    success_threshold: int = 2                  # succes HALF_OPEN avant CLOSED
    cooldown_seconds: float = 30.0              # attente OPEN -> HALF_OPEN
    half_open_max_calls: int = 1                # appels parallel en HALF_OPEN
    expected_exceptions: tuple[type[BaseException], ...] = (Exception,)

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.success_threshold < 1:
            raise ValueError("success_threshold must be >= 1")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        if self.half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")


@dataclass
class CircuitBreakerStats:
    """Stats observabilite d'un CB."""

    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    total_calls: int = 0
    total_successes: int = 0
    total_failures: int = 0
    total_rejections: int = 0
    state_transitions: int = 0
    last_failure_message: str | None = None
    last_state_change_at: float = field(default_factory=time.monotonic)
    half_open_in_flight: int = 0


class CircuitBreaker:
    """Circuit breaker async-safe.

    Usage :
        cb = CircuitBreaker(CircuitBreakerConfig(name="stripe"))
        result = await cb.call(stripe_client.charge, amount, currency)
    """

    def __init__(self, config: CircuitBreakerConfig) -> None:
        self._config = config
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()

    # -- public API ----------------------------------------------------

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def state(self) -> CircuitState:
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        return self._stats

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute `func` sous protection du CB."""
        await self._before_call()
        try:
            result = await func(*args, **kwargs)
        except BaseException as exc:
            await self._on_failure(exc)
            raise
        else:
            await self._on_success()
            return result

    async def reset(self) -> None:
        """Force un retour a CLOSED (admin override)."""
        async with self._lock:
            self._stats.state = CircuitState.CLOSED
            self._stats.consecutive_failures = 0
            self._stats.consecutive_successes = 0
            self._stats.half_open_in_flight = 0
            self._stats.last_state_change_at = time.monotonic()
            self._stats.state_transitions += 1
            logger.info("circuit '%s' force-reset to CLOSED", self.name)

    # -- internal state transitions ------------------------------------

    async def _before_call(self) -> None:
        async with self._lock:
            self._stats.total_calls += 1

            if self._stats.state is CircuitState.OPEN:
                if self._cooldown_elapsed():
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    self._stats.total_rejections += 1
                    raise CircuitBreakerOpenError(
                        self.name,
                        last_failure=self._stats.last_failure_message,
                    )

            if self._stats.state is CircuitState.HALF_OPEN:
                if self._stats.half_open_in_flight >= (
                    self._config.half_open_max_calls
                ):
                    self._stats.total_rejections += 1
                    raise CircuitBreakerOpenError(
                        self.name,
                        last_failure="half-open limit reached",
                    )
                self._stats.half_open_in_flight += 1

    async def _on_success(self) -> None:
        async with self._lock:
            self._stats.total_successes += 1
            self._stats.consecutive_failures = 0

            if self._stats.state is CircuitState.HALF_OPEN:
                self._stats.half_open_in_flight = max(
                    0, self._stats.half_open_in_flight - 1,
                )
                self._stats.consecutive_successes += 1
                if (
                    self._stats.consecutive_successes
                    >= self._config.success_threshold
                ):
                    self._transition_to(CircuitState.CLOSED)
            else:
                self._stats.consecutive_successes += 1

    async def _on_failure(self, exc: BaseException) -> None:
        is_expected = isinstance(exc, self._config.expected_exceptions)
        async with self._lock:
            if not is_expected:
                # exception non-comptee : on ne deplace pas le state,
                # mais on libere quand meme le slot half-open.
                if self._stats.state is CircuitState.HALF_OPEN:
                    self._stats.half_open_in_flight = max(
                        0, self._stats.half_open_in_flight - 1,
                    )
                return

            self._stats.total_failures += 1
            self._stats.consecutive_successes = 0
            self._stats.consecutive_failures += 1
            self._stats.last_failure_message = (
                f"{type(exc).__name__}: {exc!s}"[:200]
            )

            if self._stats.state is CircuitState.HALF_OPEN:
                self._stats.half_open_in_flight = max(
                    0, self._stats.half_open_in_flight - 1,
                )
                self._transition_to(CircuitState.OPEN)
                return

            if (
                self._stats.state is CircuitState.CLOSED
                and self._stats.consecutive_failures
                >= self._config.failure_threshold
            ):
                self._transition_to(CircuitState.OPEN)

    def _cooldown_elapsed(self) -> bool:
        elapsed = time.monotonic() - self._stats.last_state_change_at
        return elapsed >= self._config.cooldown_seconds

    def _transition_to(self, new_state: CircuitState) -> None:
        old = self._stats.state
        if old is new_state:
            return
        self._stats.state = new_state
        self._stats.state_transitions += 1
        self._stats.last_state_change_at = time.monotonic()
        if new_state is CircuitState.CLOSED:
            self._stats.consecutive_failures = 0
            self._stats.consecutive_successes = 0
        elif new_state is CircuitState.HALF_OPEN:
            self._stats.consecutive_successes = 0
            self._stats.half_open_in_flight = 0
        logger.info(
            "circuit '%s' transition %s -> %s (failures=%d)",
            self.name, old.value, new_state.value,
            self._stats.consecutive_failures,
        )
