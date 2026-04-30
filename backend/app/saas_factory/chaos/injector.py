"""ChaosInjector : wrap un callable et injecte des defaillances.

Garde-fou critique (ADR-30) : refuse d'instancier si
`UBA_CHAOS_ENABLED` n'est pas dans l'environnement, sauf passage
explicite `enabled=True` (utilise par les tests).
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from .scenarios import ChaosScenario, FailureMode

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ChaosDisabledError(RuntimeError):
    """Leve quand on tente d'utiliser le chaos sans gate enabled."""


@dataclass(frozen=True)
class InjectionEvent:
    """Trace d'une injection — pour assertions tests."""

    scenario_name: str
    failure_mode: FailureMode | None       # None si pass-through
    target: str                            # nom du callable
    delayed_seconds: float = 0.0


class ChaosInjector:
    """Wrap un callable async et injecte des defaillances.

    Usage tests :
        injector = ChaosInjector(scenario, enabled=True)
        result = await injector.invoke(client.method, *args)
        assert injector.events[-1].failure_mode is FailureMode.ERROR

    Usage staging :
        export UBA_CHAOS_ENABLED=1
        injector = ChaosInjector(scenario)
        await injector.invoke(...)
    """

    _ENV_GATE: str = "UBA_CHAOS_ENABLED"

    def __init__(
        self,
        scenario: ChaosScenario,
        *,
        enabled: bool | None = None,
    ) -> None:
        if enabled is None:
            enabled = os.environ.get(self._ENV_GATE, "0").strip() == "1"
        if not enabled:
            raise ChaosDisabledError(
                f"chaos injection blocked: set {self._ENV_GATE}=1 "
                "or pass enabled=True (tests only)",
            )
        self._scenario = scenario
        self._rng = (
            secrets.SystemRandom()
            if scenario.seed is None
            else _SeededRandom(scenario.seed)
        )
        self.events: list[InjectionEvent] = []

    @property
    def scenario(self) -> ChaosScenario:
        return self._scenario

    async def invoke(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute `func` avec injection chaos selon scenario."""
        target = getattr(func, "__qualname__", repr(func))

        # Probabilite — si pas declenche, pass-through
        if self._rng.random() >= self._scenario.failure_probability:
            self.events.append(
                InjectionEvent(
                    scenario_name=self._scenario.name,
                    failure_mode=None,
                    target=target,
                ),
            )
            return await func(*args, **kwargs)

        mode = self._rng.choice(list(self._scenario.failure_modes))
        delay = self._scenario.delay_seconds

        # Delay avant injection (simule slowness)
        if delay > 0:
            await asyncio.sleep(delay)

        self.events.append(
            InjectionEvent(
                scenario_name=self._scenario.name,
                failure_mode=mode,
                target=target,
                delayed_seconds=delay,
            ),
        )
        logger.info(
            "chaos inject %s on %s (delay=%.2fs)",
            mode.value, target, delay,
        )
        return await self._apply_mode(mode, func, args, kwargs)

    async def _apply_mode(
        self,
        mode: FailureMode,
        func: Callable[..., Awaitable[T]],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> T:
        if mode is FailureMode.TIMEOUT:
            raise TimeoutError("[chaos] simulated timeout")

        if mode is FailureMode.ERROR:
            raise RuntimeError("[chaos] simulated runtime error")

        if mode is FailureMode.CONNECTION_RESET:
            raise ConnectionResetError("[chaos] simulated connection reset")

        if mode is FailureMode.RATE_LIMITED:
            err = RuntimeError("[chaos] simulated rate limit (HTTP 429)")
            err.status_code = 429        # type: ignore[attr-defined]
            raise err

        if mode is FailureMode.AUTH_FAILURE:
            err = RuntimeError("[chaos] simulated auth failure (HTTP 401)")
            err.status_code = 401        # type: ignore[attr-defined]
            raise err

        if mode is FailureMode.SLOW_RESPONSE:
            # delay deja applique au-dessus, on poursuit l'appel
            return await func(*args, **kwargs)

        if mode is FailureMode.PARTIAL_DATA:
            real = await func(*args, **kwargs)
            return _truncate(real)        # type: ignore[return-value]

        # Should not happen — exhaustive enum
        raise NotImplementedError(f"failure mode {mode!r} not handled")


def _truncate(value: Any) -> Any:
    """Renvoie une version tronquee de la valeur (PARTIAL_DATA mode)."""
    if isinstance(value, dict):
        # vire la moitie des cles
        keys = list(value.keys())
        return {k: value[k] for k in keys[: len(keys) // 2]}
    if isinstance(value, list | tuple):
        n = len(value) // 2
        return type(value)(value[:n])
    if isinstance(value, str):
        return value[: len(value) // 2]
    if value is None:
        return None
    # type non gere : retourne None pour simuler "missing field"
    return None


class _SeededRandom:
    """Wrapper minimal pour `random.Random` seede deterministe.

    On prefere ne pas importer `random` au top-level (Bandit B311),
    donc on encapsule.
    """

    def __init__(self, seed: int) -> None:
        import random as _random
        self._r = _random.Random(seed)

    def random(self) -> float:
        return self._r.random()

    def choice(self, seq: list[Any]) -> Any:
        return self._r.choice(seq)
