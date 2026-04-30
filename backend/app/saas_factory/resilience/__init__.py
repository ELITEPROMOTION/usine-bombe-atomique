"""Phase 9L resilience patterns.

Outillage in-memory pour proteger les call-sites V9 contre les
defaillances des dependances externes (Stripe, Hostinger, Anthropic, DB).

Modules :
- circuit_breaker : CB async-safe avec etats CLOSED/OPEN/HALF_OPEN.
- timeouts : TimeoutPolicy + helper `with_timeout`.
- kill_switch : registry env-based pour fail-fast manuel.
- policies : catalogue des politiques par dependance V9.
"""
from __future__ import annotations

from .circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
)
from .kill_switch import KillSwitchRegistry, get_kill_switches
from .policies import RESILIENCE_POLICIES, ResiliencePolicy, get_policy
from .timeouts import TimeoutError as ResilienceTimeoutError
from .timeouts import TimeoutPolicy, with_timeout

__all__ = (
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "KillSwitchRegistry",
    "get_kill_switches",
    "RESILIENCE_POLICIES",
    "ResiliencePolicy",
    "get_policy",
    "ResilienceTimeoutError",
    "TimeoutPolicy",
    "with_timeout",
)
