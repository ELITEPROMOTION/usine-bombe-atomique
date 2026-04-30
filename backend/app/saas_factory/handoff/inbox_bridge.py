"""Pont vers l'inbox d'Ahmed pour les handoffs.

`InboxBridge` est un Protocol minimaliste : `post()` recoit un payload
prepare par l'orchestrateur (titre, body, lien direct, locale) et le
publie ou la ou l'admin le consultera.

`LoggingInboxBridge` est l'implementation par defaut : elle journalise
sans rien envoyer. C'est ce qui est utilise dans les tests et tant que
l'integration reelle (table `ahmed_inbox` ou Slack) n'est pas branchee.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InboxItem:
    project_id: str
    handoff_id: str            # UUID en str pour serialisation
    action_type: str
    title: str
    body: str
    cta_url: str
    locale: str
    metadata: dict[str, Any] = field(default_factory=dict)


class InboxBridge(Protocol):
    async def post(self, item: InboxItem) -> None: ...


class LoggingInboxBridge:
    """Bridge par defaut : ne fait que logger. Aucun side-effect externe."""

    def __init__(self) -> None:
        self.posted: list[InboxItem] = []

    async def post(self, item: InboxItem) -> None:
        self.posted.append(item)
        logger.info(
            "inbox_post project=%s handoff=%s action=%s locale=%s",
            item.project_id, item.handoff_id, item.action_type, item.locale,
        )
