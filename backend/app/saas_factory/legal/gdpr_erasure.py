"""GDPREraser : Article 17 (right to be forgotten) avec retention 17§3.

Strategy :
1. `request_erasure` : enregistre la demande dans `data_erasure_requests`
   (status='pending'). 30j de delai legal pour reverser si demande
   accidentelle ou frauduleuse.
2. `execute_erasure` (apres 30j) : anonymise les colonnes PII des tables
   user-facing :
   - projects.owner_email -> 'erased@redacted.local'
   - projects.company_name -> '[ERASED]'
   - projects.summary_json -> {'erased': true}
   - payments.owner_email, invoices.owner_email -> idem
   - handoff_requests.target_email -> 'erased@redacted.local'
3. **Preserve** les tables d'audit immutable (Art 17§3 obligation legale) :
   - mandates : signatures, timestamp, hash chain — pas touche
   - evidence_ledger : pas touche
   - admin_actions : pas touche
   - ai_decisions_log : pas touche (prompt_hash, pas le prompt brut)
   - audit_events : pas touche

Le client peut etre informe : "Vos donnees personnelles ont ete
anonymisees. L'audit trail est conserve sous obligation legale (Art
17§3 GDPR) pour une duree de 7 ans."
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


REVERSAL_WINDOW = timedelta(days=30)
ERASED_EMAIL_PLACEHOLDER = "erased@redacted.local"
ERASED_TEXT_PLACEHOLDER = "[ERASED]"


class ErasureStatus(str, enum.Enum):
    PENDING = "pending"            # demandee, dans la fenetre de 30j
    EXECUTED = "executed"          # anonymisation effectuee
    CANCELLED = "cancelled"        # rev. avant execution
    BLOCKED = "blocked"            # legal hold (litige en cours)


class ErasureNotPermittedError(RuntimeError):
    """Erasure refusee — legal hold ou status incompatible."""


@dataclass(frozen=True)
class ErasureRecord:
    request_id: UUID
    project_id: UUID
    requested_at: datetime
    executable_after: datetime         # requested_at + 30j
    executed_at: datetime | None
    status: ErasureStatus
    reason: str
    requester_email: str | None


class GDPREraser:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def request_erasure(
        self,
        *,
        project_id: UUID,
        reason: str,
        requester_email: str | None = None,
    ) -> ErasureRecord:
        """Enregistre une demande d'erasure (sans executer)."""
        if not reason.strip():
            raise ValueError("reason requis (Art 13 — info au sujet)")

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT request_id FROM data_erasure_requests
                 WHERE project_id = $1 AND status = 'pending'
                """,
                project_id,
            )
            if existing is not None:
                raise ErasureNotPermittedError(
                    f"erasure deja demandee pour project {project_id}",
                )

            project_row = await conn.fetchrow(
                "SELECT 1 FROM projects WHERE project_id = $1", project_id,
            )
            if project_row is None:
                raise LookupError(f"project {project_id} introuvable")

            now = datetime.now(UTC)
            executable_after = now + REVERSAL_WINDOW
            row = await conn.fetchrow(
                """
                INSERT INTO data_erasure_requests (
                    project_id, status, reason, requester_email,
                    requested_at, executable_after
                ) VALUES ($1, 'pending', $2, $3, $4, $5)
                RETURNING request_id
                """,
                project_id, reason[:500],
                (requester_email or "").lower() or None,
                now, executable_after,
            )

        logger.info(
            "gdpr.erasure_requested project=%s executable_after=%s",
            project_id, executable_after.isoformat(),
        )
        return ErasureRecord(
            request_id=row["request_id"],
            project_id=project_id,
            requested_at=now,
            executable_after=executable_after,
            executed_at=None,
            status=ErasureStatus.PENDING,
            reason=reason,
            requester_email=requester_email,
        )

    async def cancel_erasure(self, request_id: UUID) -> bool:
        """Annule une demande pending (avant executable_after)."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE data_erasure_requests
                   SET status = 'cancelled', cancelled_at = NOW()
                 WHERE request_id = $1 AND status = 'pending'
                RETURNING request_id
                """,
                request_id,
            )
        return row is not None

    async def execute_erasure(
        self,
        request_id: UUID,
        *,
        force: bool = False,
    ) -> dict[str, int]:
        """Execute l'erasure (anonymise les colonnes PII).

        `force=True` permet d'executer avant `executable_after` (admin
        override, e.g. demande urgente RGPD-litige).
        """
        async with self._pool.acquire() as conn, conn.transaction():
            req = await conn.fetchrow(
                """
                SELECT project_id, executable_after, status
                  FROM data_erasure_requests
                 WHERE request_id = $1 FOR UPDATE
                """,
                request_id,
            )
            if req is None:
                raise LookupError(f"erasure request {request_id} introuvable")
            if req["status"] != "pending":
                raise ErasureNotPermittedError(
                    f"erasure status={req['status']!r}, pas executable",
                )
            now = datetime.now(UTC)
            if not force and req["executable_after"] > now:
                raise ErasureNotPermittedError(
                    f"executable_after={req['executable_after']} pas encore atteint",
                )

            project_id = req["project_id"]

            # Anonymise les colonnes PII user-facing.
            counts: dict[str, int] = {}

            # 1. projects (owner_email + company + summary)
            r = await conn.execute(
                """
                UPDATE projects
                   SET owner_email = $2,
                       company_name = $3,
                       summary_json = '{"erased":true}'::jsonb,
                       status = 'archived',
                       archived_at = NOW(),
                       updated_at = NOW()
                 WHERE project_id = $1
                """,
                project_id, ERASED_EMAIL_PLACEHOLDER, ERASED_TEXT_PLACEHOLDER,
            )
            counts["projects"] = _parse_update_count(r)

            # 2. payments (owner_email)
            r = await conn.execute(
                """
                UPDATE payments
                   SET owner_email = $2, updated_at = NOW()
                 WHERE project_id = $1
                """,
                project_id, ERASED_EMAIL_PLACEHOLDER,
            )
            counts["payments"] = _parse_update_count(r)

            # 3. invoices (owner_email + description)
            r = await conn.execute(
                """
                UPDATE invoices
                   SET owner_email = $2, description = $3
                 WHERE project_id = $1
                """,
                project_id, ERASED_EMAIL_PLACEHOLDER, ERASED_TEXT_PLACEHOLDER,
            )
            counts["invoices"] = _parse_update_count(r)

            # 4. handoff_requests (target_email)
            r = await conn.execute(
                """
                UPDATE handoff_requests
                   SET target_email = $2, updated_at = NOW()
                 WHERE project_id = $1
                """,
                project_id, ERASED_EMAIL_PLACEHOLDER,
            )
            counts["handoff_requests"] = _parse_update_count(r)

            # 5. client_onboarding_sessions (owner_email + partial_data_json)
            r = await conn.execute(
                """
                UPDATE client_onboarding_sessions
                   SET owner_email = $2,
                       partial_data_json = '{"erased":true}'::jsonb,
                       updated_at = NOW()
                 WHERE project_id = $1
                """,
                project_id, ERASED_EMAIL_PLACEHOLDER,
            )
            counts["onboarding_sessions"] = _parse_update_count(r)

            # 6. Mark erasure as executed
            await conn.execute(
                """
                UPDATE data_erasure_requests
                   SET status = 'executed', executed_at = NOW(),
                       counts_json = $2::jsonb
                 WHERE request_id = $1
                """,
                request_id,
                _to_json(counts),
            )

        logger.info(
            "gdpr.erasure_executed project=%s force=%s counts=%s",
            project_id, force, counts,
        )
        return counts

    async def get_erasure(self, request_id: UUID) -> ErasureRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT request_id, project_id, requested_at,
                       executable_after, executed_at, status,
                       reason, requester_email
                  FROM data_erasure_requests
                 WHERE request_id = $1
                """,
                request_id,
            )
        if row is None:
            return None
        return ErasureRecord(
            request_id=row["request_id"],
            project_id=row["project_id"],
            requested_at=row["requested_at"],
            executable_after=row["executable_after"],
            executed_at=row["executed_at"],
            status=ErasureStatus(row["status"]),
            reason=row["reason"],
            requester_email=row["requester_email"],
        )


def _parse_update_count(result: str) -> int:
    """asyncpg renvoie 'UPDATE N' sous forme de string."""
    if not isinstance(result, str):
        return 0
    parts = result.strip().split()
    if len(parts) < 2:
        return 0
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


def _to_json(d: dict[str, Any]) -> str:
    import json
    return json.dumps(d, sort_keys=True, ensure_ascii=False, default=str)
