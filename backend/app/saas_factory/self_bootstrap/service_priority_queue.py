"""Module D : file de priorite logique pour l'activation des services tiers.

Ordre impose par le CDC V9 :
  Tier 1 (no_kyc)        : Cloudflare, GitHub, Resend, Sentry, PostHog
  Tier 2 (carte requise) : Datadog, Crisp        -> handoff carte Ahmed
  Tier 3 (KYC business)  : Stripe                -> handoff KYC ~5 min

Cette file est purement metier (in-memory) : elle ne remplace pas l'Arq
worker queue d'infrastructure. Elle resout l'ordre, les dependances
inter-services, le retry exponential, et detecte les boucles infructueuses.
"""
from __future__ import annotations

import enum
import heapq
import itertools
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


class ServiceTier(int, enum.Enum):
    NO_KYC = 1          # zero info bancaire / identite
    CARD_REQUIRED = 2   # carte de paiement seule
    KYC_BUSINESS = 3    # justificatifs business


@dataclass(frozen=True)
class ServiceDescriptor:
    name: str
    tier: ServiceTier
    depends_on: tuple[str, ...] = ()
    max_attempts: int = 5


# Catalogue par defaut V9 (extensible).
DEFAULT_CATALOG: tuple[ServiceDescriptor, ...] = (
    ServiceDescriptor("cloudflare", ServiceTier.NO_KYC),
    ServiceDescriptor("github", ServiceTier.NO_KYC),
    ServiceDescriptor("resend", ServiceTier.NO_KYC),
    ServiceDescriptor("sentry", ServiceTier.NO_KYC),
    ServiceDescriptor("posthog", ServiceTier.NO_KYC),
    ServiceDescriptor("datadog", ServiceTier.CARD_REQUIRED, depends_on=("sentry",)),
    ServiceDescriptor("crisp", ServiceTier.CARD_REQUIRED),
    ServiceDescriptor(
        "stripe",
        ServiceTier.KYC_BUSINESS,
        depends_on=("cloudflare", "resend"),
    ),
)


@dataclass
class _PendingItem:
    service: ServiceDescriptor
    attempt: int = 0
    next_run_at: float = 0.0
    last_error: str | None = None
    consecutive_identical_failures: int = 0


class LoopDetectedError(RuntimeError):
    """Raised when the same failure repeats > threshold (anti-boucle)."""


class ServicePriorityQueue:
    """Min-heap (tier, attempt, seq) avec dependances et retry exponential.

    `next()` retourne le prochain service a activer ou None si rien n'est
    pret (toutes les dependances ouvertes, ou backoff actif).
    """

    LOOP_THRESHOLD = 3
    BASE_BACKOFF_S = 2.0

    def __init__(
        self,
        catalog: tuple[ServiceDescriptor, ...] = DEFAULT_CATALOG,
        clock: Any = time.monotonic,
    ) -> None:
        self._clock = clock
        self._items: dict[str, _PendingItem] = {p.name: _PendingItem(p) for p in catalog}
        self._activated: set[str] = set()
        self._failed_permanent: set[str] = set()
        self._counter = itertools.count()
        self._heap: list[tuple[int, int, int, str]] = []
        self._rebuild_heap()

    # --- private ---
    def _rebuild_heap(self) -> None:
        self._heap = []
        for name, item in self._items.items():
            if name in self._activated or name in self._failed_permanent:
                continue
            heapq.heappush(
                self._heap,
                (item.service.tier.value, item.attempt, next(self._counter), name),
            )

    def _deps_satisfied(self, item: _PendingItem) -> bool:
        return all(d in self._activated for d in item.service.depends_on)

    # --- public ---
    def next(self) -> ServiceDescriptor | None:
        now = self._clock()
        # On parcourt le heap en re-poussant les non-prets pour preserver l'ordre.
        deferred: list[tuple[int, int, int, str]] = []
        chosen: ServiceDescriptor | None = None
        while self._heap:
            entry = heapq.heappop(self._heap)
            name = entry[3]
            item = self._items[name]
            if name in self._activated or name in self._failed_permanent:
                continue
            if item.next_run_at > now or not self._deps_satisfied(item):
                deferred.append(entry)
                continue
            chosen = item.service
            break
        for d in deferred:
            heapq.heappush(self._heap, d)
        return chosen

    def mark_success(self, name: str) -> None:
        if name not in self._items:
            raise KeyError(name)
        self._activated.add(name)
        item = self._items[name]
        item.last_error = None
        item.consecutive_identical_failures = 0

    def mark_failure(self, name: str, error: str) -> bool:
        """Enregistre un echec, planifie un retry exponentiel.

        Retourne True si on retentera plus tard, False si on abandonne
        (max_attempts atteint ou boucle detectee).
        """
        if name not in self._items:
            raise KeyError(name)
        item = self._items[name]
        item.attempt += 1
        if item.last_error == error:
            item.consecutive_identical_failures += 1
        else:
            item.consecutive_identical_failures = 1
        item.last_error = error

        if item.consecutive_identical_failures >= self.LOOP_THRESHOLD:
            logger.warning(
                "loop detected on %s (%dx '%s') -> abandon",
                name, item.consecutive_identical_failures, error[:80],
            )
            self._failed_permanent.add(name)
            return False

        if item.attempt >= item.service.max_attempts:
            logger.warning("%s : max attempts reached -> abandon", name)
            self._failed_permanent.add(name)
            return False

        backoff = self.BASE_BACKOFF_S * (2 ** (item.attempt - 1))
        item.next_run_at = self._clock() + backoff
        heapq.heappush(
            self._heap,
            (item.service.tier.value, item.attempt, next(self._counter), name),
        )
        return True

    def status(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "tier": item.service.tier.value,
                "attempt": item.attempt,
                "activated": name in self._activated,
                "failed_permanent": name in self._failed_permanent,
                "depends_on": list(item.service.depends_on),
                "last_error": item.last_error,
                "deps_satisfied": self._deps_satisfied(item),
            }
            for name, item in self._items.items()
        }

    @property
    def is_complete(self) -> bool:
        return all(
            n in self._activated or n in self._failed_permanent for n in self._items
        )
