"""Machine d'etat pour les handoffs unifies (Phase 9E).

Transitions autorisees :

    REQUESTED ──► NOTIFIED ──► ACKNOWLEDGED ──► RESOLVED
                     │              │
                     └──► EXPIRED ◄─┘
                     │
                     └──► ESCALATED
                     │
    REQUESTED ──► CANCELLED
    NOTIFIED  ──► CANCELLED
    ACKNOWLEDGED ──► CANCELLED

Etats terminaux : RESOLVED, EXPIRED, CANCELLED. Aucune transition possible
depuis un etat terminal.
"""
from __future__ import annotations

import enum
from typing import Final


class HandoffState(str, enum.Enum):
    REQUESTED = "requested"          # cree mais pas encore notifie
    NOTIFIED = "notified"            # email/inbox envoye
    ACKNOWLEDGED = "acknowledged"    # user a vu le lien (1er click)
    RESOLVED = "resolved"            # user a complete l'action
    EXPIRED = "expired"              # TTL depasse
    ESCALATED = "escalated"          # alerte Slack apres timeout
    CANCELLED = "cancelled"          # annule manuellement


_VALID_TRANSITIONS: Final[dict[HandoffState, frozenset[HandoffState]]] = {
    HandoffState.REQUESTED: frozenset({
        HandoffState.NOTIFIED,
        HandoffState.CANCELLED,
        HandoffState.EXPIRED,
    }),
    HandoffState.NOTIFIED: frozenset({
        HandoffState.ACKNOWLEDGED,
        HandoffState.EXPIRED,
        HandoffState.ESCALATED,
        HandoffState.CANCELLED,
    }),
    HandoffState.ACKNOWLEDGED: frozenset({
        HandoffState.RESOLVED,
        HandoffState.EXPIRED,
        HandoffState.ESCALATED,
        HandoffState.CANCELLED,
    }),
    HandoffState.ESCALATED: frozenset({
        HandoffState.RESOLVED,
        HandoffState.EXPIRED,
        HandoffState.CANCELLED,
    }),
    # Terminaux : aucune transition.
    HandoffState.RESOLVED: frozenset(),
    HandoffState.EXPIRED: frozenset(),
    HandoffState.CANCELLED: frozenset(),
}


TERMINAL_STATES: Final[frozenset[HandoffState]] = frozenset({
    HandoffState.RESOLVED,
    HandoffState.EXPIRED,
    HandoffState.CANCELLED,
})


def is_valid_transition(from_state: HandoffState, to_state: HandoffState) -> bool:
    """True si la transition est autorisee."""
    return to_state in _VALID_TRANSITIONS.get(from_state, frozenset())


def next_states(from_state: HandoffState) -> frozenset[HandoffState]:
    """Ensemble des etats accessibles depuis `from_state`."""
    return _VALID_TRANSITIONS.get(from_state, frozenset())


def is_terminal(state: HandoffState) -> bool:
    return state in TERMINAL_STATES
