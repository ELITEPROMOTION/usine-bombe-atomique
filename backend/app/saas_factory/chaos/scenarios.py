"""ChaosScenario : catalogue des modes de defaillance pour drills V9.

Chaque scenario est une **specification deterministe** (probabilite
fixe + seed) que l'injector applique aux callables wrappes.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Final


class FailureMode(str, enum.Enum):
    TIMEOUT = "timeout"                        # injection asyncio.TimeoutError
    ERROR = "error"                            # exception generique
    SLOW_RESPONSE = "slow_response"            # ajoute un delay
    PARTIAL_DATA = "partial_data"              # retourne data tronquee
    CONNECTION_RESET = "connection_reset"      # ConnectionResetError
    RATE_LIMITED = "rate_limited"              # 429-like
    AUTH_FAILURE = "auth_failure"              # 401-like


@dataclass(frozen=True)
class ChaosScenario:
    """Specification immutable d'un scenario de chaos."""

    name: str
    description: str
    failure_modes: tuple[FailureMode, ...]
    failure_probability: float = 1.0           # 0..1
    delay_seconds: float = 0.0                 # ajoute si SLOW_RESPONSE
    seed: int | None = None                    # determinisme tests
    target_dependencies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not 0.0 <= self.failure_probability <= 1.0:
            raise ValueError(
                "failure_probability must be in [0, 1]",
            )
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        if not self.failure_modes:
            raise ValueError("at least one failure_mode required")


# ---------------------------------------------------------------------------
# Catalogue V9
# ---------------------------------------------------------------------------
CHAOS_SCENARIOS: Final[dict[str, ChaosScenario]] = {
    "stripe_down": ChaosScenario(
        name="stripe_down",
        description="Stripe API totalement injoignable",
        failure_modes=(FailureMode.CONNECTION_RESET,),
        failure_probability=1.0,
        target_dependencies=("stripe",),
    ),
    "stripe_intermittent": ChaosScenario(
        name="stripe_intermittent",
        description="Stripe a 30% d'erreurs (instabilite)",
        failure_modes=(FailureMode.ERROR, FailureMode.TIMEOUT),
        failure_probability=0.3,
        seed=42,
        target_dependencies=("stripe",),
    ),
    "hostinger_dns_slow": ChaosScenario(
        name="hostinger_dns_slow",
        description="Hostinger DNS update repond lentement",
        failure_modes=(FailureMode.SLOW_RESPONSE,),
        failure_probability=1.0,
        delay_seconds=2.0,
        target_dependencies=("hostinger",),
    ),
    "anthropic_rate_limit": ChaosScenario(
        name="anthropic_rate_limit",
        description="Anthropic 429 systematique",
        failure_modes=(FailureMode.RATE_LIMITED,),
        failure_probability=1.0,
        target_dependencies=("anthropic",),
    ),
    "anthropic_auth_failure": ChaosScenario(
        name="anthropic_auth_failure",
        description="Anthropic 401 (cle invalide / revoquee)",
        failure_modes=(FailureMode.AUTH_FAILURE,),
        failure_probability=1.0,
        target_dependencies=("anthropic",),
    ),
    "db_pool_exhausted": ChaosScenario(
        name="db_pool_exhausted",
        description="Pool DB sature, timeout sur acquire",
        failure_modes=(FailureMode.TIMEOUT,),
        failure_probability=1.0,
        delay_seconds=1.0,
        target_dependencies=("postgres",),
    ),
    "partial_failure": ChaosScenario(
        name="partial_failure",
        description="50% des appels echouent (test idempotency)",
        failure_modes=(FailureMode.ERROR,),
        failure_probability=0.5,
        seed=1337,
    ),
    "resend_silent_drop": ChaosScenario(
        name="resend_silent_drop",
        description="Resend renvoie data tronquee (mail send id manquant)",
        failure_modes=(FailureMode.PARTIAL_DATA,),
        failure_probability=1.0,
        target_dependencies=("resend",),
    ),
}


def get_scenario(name: str) -> ChaosScenario:
    """Retourne le scenario `name` ou KeyError."""
    if name not in CHAOS_SCENARIOS:
        raise KeyError(
            f"unknown scenario '{name}', "
            f"known: {sorted(CHAOS_SCENARIOS.keys())}",
        )
    return CHAOS_SCENARIOS[name]
