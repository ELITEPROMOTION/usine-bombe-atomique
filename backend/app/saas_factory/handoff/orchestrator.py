"""Orchestrateur unifie des handoffs.

API :
- `request(...)`  : cree un handoff + emet un direct_link + post inbox optionnel
- `notify(handoff_id)` : passe REQUESTED -> NOTIFIED (apres envoi)
- `acknowledge(token)` : passe NOTIFIED -> ACKNOWLEDGED (apres 1er click)
- `resolve(token, payload?)` : passe -> RESOLVED + execute callback enregistre
- `escalate(handoff_id)` : passe NOTIFIED/ACKNOWLEDGED -> ESCALATED (apres timeout)
- `cancel(handoff_id, reason)` : passe -> CANCELLED
- `tick()` : balaie les handoffs expires/a relancer (a appeler via Arq)
- `register_resolution_callback(action_type, cb)` : enregistre un handler
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.direct_links.action_card_generator import (
    ActionCardGenerator,
)
from app.saas_factory.direct_links.catalog import Catalog
from app.saas_factory.direct_links.direct_link_generator import (
    DirectLinkGenerator,
    IssuedLink,
)
from app.saas_factory.direct_links.validation_engine import (
    LinkResolution,
    LinkStatus,
    ValidationEngine,
)
from app.saas_factory.handoff.inbox_bridge import InboxBridge, InboxItem
from app.saas_factory.handoff.state_machine import (
    HandoffState,
    is_terminal,
    is_valid_transition,
)

logger = logging.getLogger(__name__)


DEFAULT_ESCALATION_AFTER = timedelta(hours=24)


class HandoffNotFoundError(LookupError):
    pass


class InvalidTransitionError(RuntimeError):
    def __init__(self, from_state: HandoffState, to_state: HandoffState) -> None:
        super().__init__(
            f"transition invalide : {from_state.value} -> {to_state.value}"
        )
        self.from_state = from_state
        self.to_state = to_state


# Signature : cb(handoff_id, action_type, project_id, payload) -> None
ResolutionCallback = Callable[[UUID, str, str, dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class HandoffRequest:
    handoff_id: UUID
    project_id: str
    action_type: str
    state: HandoffState
    target_email: str
    locale: str
    direct_link_id: UUID
    payload: dict[str, Any]
    issued_token: str | None       # uniquement renvoye lors du request initial
    cta_url: str
    title: str
    body: str
    expires_at: datetime
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_payload: dict[str, Any] = field(default_factory=dict)


class HandoffOrchestrator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        link_generator: DirectLinkGenerator,
        validation_engine: ValidationEngine,
        action_card_generator: ActionCardGenerator,
        catalog: Catalog,
        inbox_bridge: InboxBridge | None = None,
        escalation_after: timedelta = DEFAULT_ESCALATION_AFTER,
    ) -> None:
        self._pool = pool
        self._gen = link_generator
        self._val = validation_engine
        self._cards = action_card_generator
        self._catalog = catalog
        self._inbox = inbox_bridge
        self._escalation_after = escalation_after
        self._callbacks: dict[str, ResolutionCallback] = {}

    def register_resolution_callback(
        self, action_type: str, callback: ResolutionCallback,
    ) -> None:
        if not self._catalog.has(action_type):
            raise ValueError(f"action_type inconnu du catalog: {action_type!r}")
        self._callbacks[action_type] = callback

    # -----------------------------------------------------------------------
    # Cycle principal
    # -----------------------------------------------------------------------
    async def request(
        self,
        *,
        project_id: str,
        action_type: str,
        target_email: str,
        locale: str = "en",
        payload: dict[str, Any] | None = None,
        ttl: timedelta | None = None,
    ) -> HandoffRequest:
        """Cree un handoff REQUESTED + un direct_link."""
        if not self._catalog.has(action_type):
            raise ValueError(f"action_type inconnu: {action_type!r}")

        meta = dict(payload or {})
        link: IssuedLink = await self._gen.issue(
            action_type=action_type,
            target_id="",     # rempli plus tard avec handoff_id
            principal_id=None,
            metadata={"project_id": project_id, **meta},
            ttl=ttl,
        )
        # On rendr la card pour stocker title/body sterilises (renderable plus tard)
        card = self._cards.render(link, locale=locale, context=meta)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO handoff_requests (
                    project_id, action_type, state, target_email, locale,
                    direct_link_id, payload_json, title, body, cta_url,
                    expires_at
                ) VALUES (
                    $1, $2, 'requested', $3, $4,
                    $5, $6::jsonb, $7, $8, $9, $10
                ) RETURNING handoff_id, created_at
                """,
                project_id, action_type, target_email, locale,
                link.link_id,
                json.dumps(meta, sort_keys=True, ensure_ascii=False, default=str),
                card.title, card.description, link.url,
                link.expires_at,
            )
            handoff_id: UUID = row["handoff_id"]
            # On met a jour le target_id du direct_link (FK informelle).
            await conn.execute(
                "UPDATE direct_links SET target_id = $2 WHERE link_id = $1",
                link.link_id, str(handoff_id),
            )

        logger.info(
            "handoff.requested id=%s project=%s action=%s",
            handoff_id, project_id, action_type,
        )

        return HandoffRequest(
            handoff_id=handoff_id,
            project_id=project_id,
            action_type=action_type,
            state=HandoffState.REQUESTED,
            target_email=target_email,
            locale=card.locale,
            direct_link_id=link.link_id,
            payload=meta,
            issued_token=link.token,
            cta_url=link.url,
            title=card.title,
            body=card.description,
            expires_at=link.expires_at,
            created_at=row["created_at"],
        )

    async def notify(
        self,
        handoff_id: UUID,
        *,
        post_to_inbox: bool = True,
    ) -> None:
        """Passe REQUESTED -> NOTIFIED. Optionnellement publie a l'inbox."""
        await self._transition(handoff_id, HandoffState.NOTIFIED)
        if post_to_inbox and self._inbox is not None:
            req = await self.get(handoff_id)
            await self._inbox.post(InboxItem(
                project_id=req.project_id,
                handoff_id=str(handoff_id),
                action_type=req.action_type,
                title=req.title,
                body=req.body,
                cta_url=req.cta_url,
                locale=req.locale,
                metadata=req.payload,
            ))

    async def acknowledge(self, token: str) -> HandoffRequest | None:
        """Passe NOTIFIED -> ACKNOWLEDGED (le user a clique). Retourne le req."""
        resolution: LinkResolution = await self._val.validate(token)
        if resolution.status is not LinkStatus.VALID:
            return None
        if resolution.target_id is None:
            return None
        try:
            handoff_id = UUID(resolution.target_id)
        except ValueError:
            return None
        try:
            await self._transition(
                handoff_id, HandoffState.ACKNOWLEDGED,
                allow_idempotent=True,
            )
        except HandoffNotFoundError:
            return None
        return await self.get(handoff_id)

    async def resolve(
        self,
        token: str,
        *,
        resolution_payload: dict[str, Any] | None = None,
    ) -> HandoffRequest | None:
        """Consomme le token, passe ACKNOWLEDGED/NOTIFIED -> RESOLVED + callback."""
        consumed = await self._val.consume(token)
        if consumed.status is not LinkStatus.CONSUMED or consumed.target_id is None:
            return None
        try:
            handoff_id = UUID(consumed.target_id)
        except ValueError:
            return None

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE handoff_requests
                   SET state = 'resolved',
                       resolved_at = NOW(),
                       resolution_payload_json = $2::jsonb,
                       updated_at = NOW()
                 WHERE handoff_id = $1
                   AND state IN ('notified','acknowledged','escalated')
                RETURNING action_type, project_id
                """,
                handoff_id,
                json.dumps(resolution_payload or {}, sort_keys=True,
                           ensure_ascii=False, default=str),
            )
        if row is None:
            return None

        cb = self._callbacks.get(row["action_type"])
        if cb is not None:
            try:
                await cb(handoff_id, row["action_type"], row["project_id"],
                         resolution_payload or {})
            except Exception as exc:
                logger.exception("handoff resolution callback failed: %s", exc)

        logger.info("handoff.resolved id=%s action=%s",
                    handoff_id, row["action_type"])
        return await self.get(handoff_id)

    async def escalate(self, handoff_id: UUID) -> None:
        await self._transition(handoff_id, HandoffState.ESCALATED)

    async def cancel(self, handoff_id: UUID, *, reason: str = "") -> None:
        await self._transition(
            handoff_id, HandoffState.CANCELLED,
            extra_payload={"cancel_reason": reason[:500]},
        )

    async def tick(self) -> dict[str, int]:
        """Balaie les handoffs : escalade ceux non resolus apres `escalation_after`,
        marque expires ceux dont `expires_at` est passe.

        Retourne {escalated, expired}.
        """
        now = datetime.now(UTC)
        async with self._pool.acquire() as conn:
            # Escalade : NOTIFIED/ACKNOWLEDGED depuis > escalation_after
            cutoff = now - self._escalation_after
            rows = await conn.fetch(
                """
                UPDATE handoff_requests
                   SET state = 'escalated', updated_at = NOW(),
                       reminders_sent = reminders_sent + 1
                 WHERE state IN ('notified','acknowledged')
                   AND created_at <= $1
                   AND expires_at > $2
                RETURNING handoff_id
                """,
                cutoff, now,
            )
            escalated = len(rows)

            # Expiration
            rows = await conn.fetch(
                """
                UPDATE handoff_requests
                   SET state = 'expired', updated_at = NOW()
                 WHERE state IN ('requested','notified','acknowledged','escalated')
                   AND expires_at <= $1
                RETURNING handoff_id
                """,
                now,
            )
            expired = len(rows)
        return {"escalated": escalated, "expired": expired}

    async def get(self, handoff_id: UUID) -> HandoffRequest:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT handoff_id, project_id, action_type, state,
                       target_email, locale, direct_link_id, payload_json,
                       title, body, cta_url, expires_at, created_at,
                       resolved_at, resolution_payload_json
                  FROM handoff_requests
                 WHERE handoff_id = $1
                """,
                handoff_id,
            )
        if row is None:
            raise HandoffNotFoundError(f"handoff {handoff_id} introuvable")
        return _row_to_request(row)

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------
    async def _transition(
        self,
        handoff_id: UUID,
        to_state: HandoffState,
        *,
        allow_idempotent: bool = False,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "SELECT state FROM handoff_requests WHERE handoff_id = $1",
                handoff_id,
            )
            if row is None:
                raise HandoffNotFoundError(f"handoff {handoff_id} introuvable")
            current = HandoffState(row["state"])
            if allow_idempotent and current == to_state:
                return
            if not is_valid_transition(current, to_state):
                if is_terminal(current):
                    raise InvalidTransitionError(current, to_state)
                if allow_idempotent:
                    # On accepte l'idempotence pour des etats deja avances
                    # (ex. RESOLVED apres ACKNOWLEDGED).
                    return
                raise InvalidTransitionError(current, to_state)

            if extra_payload:
                await conn.execute(
                    """
                    UPDATE handoff_requests
                       SET state = $2,
                           payload_json = payload_json || $3::jsonb,
                           updated_at = NOW()
                     WHERE handoff_id = $1
                    """,
                    handoff_id, to_state.value,
                    json.dumps(extra_payload, sort_keys=True,
                               ensure_ascii=False, default=str),
                )
            else:
                await conn.execute(
                    """
                    UPDATE handoff_requests
                       SET state = $2, updated_at = NOW()
                     WHERE handoff_id = $1
                    """,
                    handoff_id, to_state.value,
                )
        logger.info("handoff.transition id=%s %s -> %s",
                    handoff_id, current.value, to_state.value)


def _row_to_request(row: asyncpg.Record) -> HandoffRequest:
    payload = row["payload_json"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    resolution = row["resolution_payload_json"]
    if isinstance(resolution, str):
        resolution = json.loads(resolution)
    return HandoffRequest(
        handoff_id=row["handoff_id"],
        project_id=row["project_id"],
        action_type=row["action_type"],
        state=HandoffState(row["state"]),
        target_email=row["target_email"],
        locale=row["locale"],
        direct_link_id=row["direct_link_id"],
        payload=payload or {},
        issued_token=None,
        cta_url=row["cta_url"],
        title=row["title"],
        body=row["body"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
        resolution_payload=resolution or {},
    )
