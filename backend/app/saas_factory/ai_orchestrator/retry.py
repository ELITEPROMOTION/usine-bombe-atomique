"""Helper de retry exponential backoff pour les appels providers IA.

Usage :
    res = await with_retry(
        lambda: provider.call(prompt="..."),
        max_attempts=3,
        base_delay=0.5,
    )

Ne reessaye que sur `TransientAIError` (ou exceptions explicitement
retriables). Une exception terminale (auth, format) coupe immediatement.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import TypeVar

# Jitter PRNG : on utilise SystemRandom pour eviter le flag bandit B311
# (random module non crypto). Pour du jitter c'est over-spec mais clean.
_JITTER_RNG = secrets.SystemRandom()

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TransientAIError(RuntimeError):
    """Exception retriable : timeout, 429, 5xx temporaire."""


class RetryExhaustedError(RuntimeError):
    """Toutes les tentatives ont echoue."""

    def __init__(self, last_exc: BaseException, attempts: int) -> None:
        super().__init__(f"retry exhausted after {attempts} attempts: {last_exc}")
        self.last_exc = last_exc
        self.attempts = attempts


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 30.0,
    jitter: bool = True,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    transient_exc: type[BaseException] | tuple[type[BaseException], ...] = TransientAIError,
) -> T:
    """Execute `coro_factory()` jusqu'a `max_attempts` fois.

    `coro_factory` est une fabrique (callable returning awaitable) plutot
    qu'un awaitable, parce qu'un awaitable n'est consommable qu'une fois.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts >= 1 requis")
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_factory()
        except transient_exc as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                delay *= 0.5 + _JITTER_RNG.random()
            logger.info(
                "retry attempt %d/%d after %.2fs (last=%s)",
                attempt, max_attempts, delay, exc,
            )
            await sleep(delay)
    if last_exc is None:
        # Invariant : on ne sort de la boucle que via except + break.
        raise RuntimeError("retry loop ended without exception (impossible)")
    raise RetryExhaustedError(last_exc, max_attempts)
