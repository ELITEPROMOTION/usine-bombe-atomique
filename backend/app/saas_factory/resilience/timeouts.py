"""TimeoutPolicy : timeouts explicites par dependance + helper async.

Plutot que de laisser asyncio default a infini, on impose des budgets
de temps explicites pour chaque categorie d'appel externe. Sentry/
Prometheus metriques peuvent suivre les violations.
"""
from __future__ import annotations

import asyncio
import builtins
import logging
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TimeoutError(asyncio.TimeoutError):
    """Re-emit avec contexte sur quelle policy a expire."""

    def __init__(self, name: str, timeout_seconds: float) -> None:
        super().__init__(
            f"timeout '{name}' expired after {timeout_seconds:.2f}s",
        )
        self.name = name
        self.timeout_seconds = timeout_seconds


@dataclass(frozen=True)
class TimeoutPolicy:
    """Budget de temps pour une dependance.

    `connect_seconds`  : temps max pour etablir la connexion.
    `total_seconds`    : temps max total (connect + read + body).
    `name`             : identifiant pour logs / metriques.
    """

    name: str
    total_seconds: float
    connect_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.total_seconds <= 0:
            raise ValueError("total_seconds must be > 0")
        if self.connect_seconds < 0:
            raise ValueError("connect_seconds must be >= 0")
        if self.connect_seconds > self.total_seconds:
            raise ValueError(
                "connect_seconds cannot exceed total_seconds",
            )


async def with_timeout(
    coro: Awaitable[T],
    policy: TimeoutPolicy,
) -> T:
    """Execute `coro` sous le budget de `policy`.

    Re-emit `TimeoutError` (notre type) au lieu de l'asyncio default,
    pour que les call-sites puissent distinguer les timeouts policy
    des autres `asyncio.TimeoutError`.
    """
    try:
        return await asyncio.wait_for(coro, timeout=policy.total_seconds)
    except builtins.TimeoutError as exc:
        logger.warning(
            "timeout policy '%s' expired (%.2fs)",
            policy.name, policy.total_seconds,
        )
        raise TimeoutError(policy.name, policy.total_seconds) from exc
