"""ResiliencePolicy catalog : (CB config + timeout) par dependance V9.

Ce catalogue permet de demarrer un CB ou un timeout coherent par
nom de dependance, sans dupliquer les chiffres dans chaque module
client.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .circuit_breaker import CircuitBreakerConfig
from .timeouts import TimeoutPolicy


@dataclass(frozen=True)
class ResiliencePolicy:
    """Politique consolidee pour une dependance externe."""

    dependency: str
    circuit: CircuitBreakerConfig
    timeout: TimeoutPolicy
    description: str = ""


# ---------------------------------------------------------------------------
# Catalogue V9
# ---------------------------------------------------------------------------
_STRIPE_CB: Final = CircuitBreakerConfig(
    name="stripe",
    failure_threshold=5,
    success_threshold=2,
    cooldown_seconds=30.0,
    half_open_max_calls=1,
)
_STRIPE_TIMEOUT: Final = TimeoutPolicy(
    name="stripe",
    total_seconds=10.0,
    connect_seconds=3.0,
)

_HOSTINGER_CB: Final = CircuitBreakerConfig(
    name="hostinger",
    failure_threshold=3,
    success_threshold=2,
    cooldown_seconds=60.0,
    half_open_max_calls=1,
)
_HOSTINGER_TIMEOUT: Final = TimeoutPolicy(
    name="hostinger",
    total_seconds=30.0,        # provisionning peut etre long
    connect_seconds=5.0,
)

_ANTHROPIC_CB: Final = CircuitBreakerConfig(
    name="anthropic",
    failure_threshold=4,
    success_threshold=2,
    cooldown_seconds=20.0,
    half_open_max_calls=2,
)
_ANTHROPIC_TIMEOUT: Final = TimeoutPolicy(
    name="anthropic",
    total_seconds=60.0,        # generation IA peut prendre 30-50s
    connect_seconds=5.0,
)

_OPENAI_CB: Final = CircuitBreakerConfig(
    name="openai",
    failure_threshold=4,
    success_threshold=2,
    cooldown_seconds=20.0,
    half_open_max_calls=2,
)
_OPENAI_TIMEOUT: Final = TimeoutPolicy(
    name="openai",
    total_seconds=60.0,
    connect_seconds=5.0,
)

_RESEND_CB: Final = CircuitBreakerConfig(
    name="resend",
    failure_threshold=5,
    success_threshold=2,
    cooldown_seconds=30.0,
)
_RESEND_TIMEOUT: Final = TimeoutPolicy(
    name="resend",
    total_seconds=10.0,
    connect_seconds=3.0,
)

_DB_CB: Final = CircuitBreakerConfig(
    name="postgres",
    failure_threshold=3,
    success_threshold=3,
    cooldown_seconds=10.0,
    half_open_max_calls=1,
)
_DB_TIMEOUT: Final = TimeoutPolicy(
    name="postgres",
    total_seconds=5.0,
    connect_seconds=2.0,
)


RESILIENCE_POLICIES: Final[dict[str, ResiliencePolicy]] = {
    "stripe": ResiliencePolicy(
        dependency="stripe",
        circuit=_STRIPE_CB,
        timeout=_STRIPE_TIMEOUT,
        description="Stripe API (charges, refunds, webhooks)",
    ),
    "hostinger": ResiliencePolicy(
        dependency="hostinger",
        circuit=_HOSTINGER_CB,
        timeout=_HOSTINGER_TIMEOUT,
        description="Hostinger API (DNS, VPS, SSL)",
    ),
    "anthropic": ResiliencePolicy(
        dependency="anthropic",
        circuit=_ANTHROPIC_CB,
        timeout=_ANTHROPIC_TIMEOUT,
        description="Anthropic Messages API",
    ),
    "openai": ResiliencePolicy(
        dependency="openai",
        circuit=_OPENAI_CB,
        timeout=_OPENAI_TIMEOUT,
        description="OpenAI Chat Completions API",
    ),
    "resend": ResiliencePolicy(
        dependency="resend",
        circuit=_RESEND_CB,
        timeout=_RESEND_TIMEOUT,
        description="Resend transactional email API",
    ),
    "postgres": ResiliencePolicy(
        dependency="postgres",
        circuit=_DB_CB,
        timeout=_DB_TIMEOUT,
        description="PostgreSQL pool",
    ),
}


def get_policy(dependency: str) -> ResiliencePolicy:
    """Retourne la politique pour `dependency` ou KeyError."""
    key = dependency.lower()
    if key not in RESILIENCE_POLICIES:
        raise KeyError(
            f"unknown dependency '{dependency}', "
            f"known: {sorted(RESILIENCE_POLICIES.keys())}",
        )
    return RESILIENCE_POLICIES[key]
