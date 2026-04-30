"""Phase 9E : Handoff Orchestrator unifie.

Couche au-dessus de :
- `direct_links`              (9A) — issue + valide les tokens
- `handoff_kyc_orchestrator`  (9-BOOT, legacy) — service activation KYC/card

Ce paquet fournit un `HandoffOrchestrator` transverse pour TOUS les types
de handoff hors service activation (review livrable, paiement, validation
domaine, escalation custom). Une `HandoffRequest` est creee avec un
direct_link sous-jacent ; sa resolution declenche un callback enregistre.
"""
from app.saas_factory.handoff.inbox_bridge import (
    InboxBridge,
    LoggingInboxBridge,
)
from app.saas_factory.handoff.orchestrator import (
    HandoffNotFoundError,
    HandoffOrchestrator,
    HandoffRequest,
    InvalidTransitionError,
    ResolutionCallback,
)
from app.saas_factory.handoff.state_machine import (
    TERMINAL_STATES,
    HandoffState,
    is_valid_transition,
    next_states,
)

__all__ = [
    "HandoffNotFoundError",
    "HandoffOrchestrator",
    "HandoffRequest",
    "HandoffState",
    "InboxBridge",
    "InvalidTransitionError",
    "LoggingInboxBridge",
    "ResolutionCallback",
    "TERMINAL_STATES",
    "is_valid_transition",
    "next_states",
]
