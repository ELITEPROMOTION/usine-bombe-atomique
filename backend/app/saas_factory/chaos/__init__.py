"""Phase 9L chaos engineering — offline-only.

ChaosInjector wraps un callable et injecte des defaillances selon un
scenario. Aucun appel reseau / DB reel n'est concerne : le module est
**uniquement** pour les tests unitaires/integration **et** les chaos
drills en staging.

ADR-30 : ChaosInjector levera systematiquement si `UBA_CHAOS_ENABLED`
n'est pas set, pour eviter qu'un commit accidentel n'introduise des
chaos en prod.
"""
from __future__ import annotations

from .injector import (
    ChaosDisabledError,
    ChaosInjector,
    InjectionEvent,
)
from .runner import run_scenario
from .scenarios import (
    CHAOS_SCENARIOS,
    ChaosScenario,
    FailureMode,
    get_scenario,
)

__all__ = (
    "CHAOS_SCENARIOS",
    "ChaosDisabledError",
    "ChaosInjector",
    "ChaosScenario",
    "FailureMode",
    "InjectionEvent",
    "get_scenario",
    "run_scenario",
)
