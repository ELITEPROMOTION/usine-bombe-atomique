"""Chaos runner : helpers async pour drills systematiques.

`run_scenario(scenario, action, repeat=N)` execute `action` N fois
sous chaos et retourne une stat des outcomes.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .injector import ChaosInjector
from .scenarios import ChaosScenario, FailureMode

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class ChaosRunReport:
    scenario: str
    iterations: int
    successes: int = 0
    failures_by_mode: dict[FailureMode, int] = field(default_factory=dict)
    pass_through: int = 0
    raised_exceptions: dict[str, int] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.iterations == 0:
            return 0.0
        return self.successes / self.iterations


async def run_scenario(
    scenario: ChaosScenario,
    action: Callable[[], Awaitable[T]],
    *,
    iterations: int = 10,
    enabled: bool = True,
) -> ChaosRunReport:
    """Execute `action` N fois sous chaos et collecte les outcomes."""
    if iterations < 1:
        raise ValueError("iterations must be >= 1")

    injector = ChaosInjector(scenario, enabled=enabled)
    report = ChaosRunReport(scenario=scenario.name, iterations=iterations)

    async def _wrapped(*args: Any, **kwargs: Any) -> T:
        return await action(*args, **kwargs)

    for _ in range(iterations):
        try:
            await injector.invoke(_wrapped)
            report.successes += 1
        except BaseException as exc:
            cls = type(exc).__name__
            report.raised_exceptions[cls] = (
                report.raised_exceptions.get(cls, 0) + 1
            )

    # Stats par mode (depuis injector.events)
    for ev in injector.events:
        if ev.failure_mode is None:
            report.pass_through += 1
        else:
            report.failures_by_mode[ev.failure_mode] = (
                report.failures_by_mode.get(ev.failure_mode, 0) + 1
            )

    return report
