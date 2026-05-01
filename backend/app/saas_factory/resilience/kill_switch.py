"""KillSwitchRegistry : fail-fast manuel via env vars.

Pattern : `UBA_KILL_<DEPENDENCY>=1` desactive immediatement les appels
a la dependance, quel que soit l'etat du circuit breaker. Utile pour :
- Couper Stripe pendant une migration de webhook.
- Bypasser un provider AI defaillant connu.
- Tests d'integration qui veulent forcer fallback.

Nominalement OFF en prod. La lecture est `os.environ.get` a chaque
check (pas de cache), pour permettre toggle a chaud par admin via
`os.environ['UBA_KILL_STRIPE'] = '1'`.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Mapping

logger = logging.getLogger(__name__)


class KillSwitchActiveError(RuntimeError):
    """Leve quand un appel est rejete par un kill switch."""

    def __init__(self, dependency: str) -> None:
        super().__init__(
            f"kill switch UBA_KILL_{dependency.upper()} is ON",
        )
        self.dependency = dependency


class KillSwitchRegistry:
    """Wrapper simple sur os.environ pour les kill switches V9."""

    _PREFIX = "UBA_KILL_"

    def __init__(
        self,
        known: Iterable[str] = (),
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._known: tuple[str, ...] = tuple(k.lower() for k in known)
        # `env` permet l'injection en tests, sinon lit os.environ live
        self._env = env

    def _read(self, key: str) -> str:
        if self._env is None:
            return os.environ.get(key, "").strip()
        return str(self._env.get(key, "")).strip()

    def is_active(self, dependency: str) -> bool:
        key = f"{self._PREFIX}{dependency.upper()}"
        return self._read(key) == "1"

    def ensure_alive(self, dependency: str) -> None:
        """Leve KillSwitchActiveError si la dependance est kill."""
        if self.is_active(dependency):
            raise KillSwitchActiveError(dependency)

    def snapshot(self) -> dict[str, bool]:
        """Etat actuel de tous les kill switches connus."""
        return {dep: self.is_active(dep) for dep in self._known}


# ---------------------------------------------------------------------------
# Singleton lazy avec catalogue connu V9
# ---------------------------------------------------------------------------
_DEFAULT_KNOWN: tuple[str, ...] = (
    "stripe",
    "hostinger",
    "anthropic",
    "openai",
    "resend",
    "n8n",
)
_singleton: KillSwitchRegistry | None = None


def get_kill_switches() -> KillSwitchRegistry:
    """Singleton du registry (lit os.environ live)."""
    global _singleton
    if _singleton is None:
        _singleton = KillSwitchRegistry(known=_DEFAULT_KNOWN)
    return _singleton
