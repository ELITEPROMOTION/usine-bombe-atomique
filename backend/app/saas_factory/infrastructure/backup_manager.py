"""BackupManager : sauvegardes quotidiennes + restore.

Operations : `schedule_daily`, `list_backups`, `restore`.
Pas de payment_id (les backups sont en general inclus dans le plan VPS).
"""
from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class BackupStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RESTORING = "restoring"
    RESTORED = "restored"


@dataclass(frozen=True)
class BackupInfo:
    backup_id: UUID
    project_id: str
    vps_resource_id: UUID
    status: BackupStatus
    size_bytes: int | None
    started_at: datetime
    completed_at: datetime | None
    hostinger_backup_id: str | None


class BackupManager:
    def __init__(self, pool: asyncpg.Pool, client: Any) -> None:
        self._pool = pool
        self._client = client

    async def schedule_daily(
        self,
        *,
        project_id: str,
        vps_resource_id: UUID,
        retention_days: int = 30,
    ) -> dict[str, Any]:
        """Active la planification quotidienne cote Hostinger."""
        if not 1 <= retention_days <= 365:
            raise ValueError("retention_days doit etre dans [1..365]")

        result = await self._client.request(
            "POST", f"/vps/instances/{vps_resource_id}/backup/schedule",
            json_body={
                "frequency": "daily",
                "retention_days": retention_days,
            },
        )
        body = result.json_body
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hostinger_audit
                    (resource_id, event, payload_json, occurred_at)
                VALUES ($1, 'backup_schedule_daily', $2::jsonb, NOW())
                """,
                vps_resource_id,
                json.dumps({"retention_days": retention_days, "raw": body},
                           sort_keys=True, ensure_ascii=False, default=str),
            )
        logger.info(
            "backup.scheduled project=%s vps=%s retention=%dj",
            project_id, vps_resource_id, retention_days,
        )
        return {"scheduled": True, "retention_days": retention_days, **body}

    async def list_backups(
        self, project_id: str, *, limit: int = 50,
    ) -> list[BackupInfo]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT backup_id, project_id, vps_resource_id, status,
                       size_bytes, started_at, completed_at, hostinger_backup_id
                  FROM backups
                 WHERE project_id = $1
                 ORDER BY started_at DESC LIMIT $2
                """,
                project_id, limit,
            )
        return [
            BackupInfo(
                backup_id=r["backup_id"], project_id=r["project_id"],
                vps_resource_id=r["vps_resource_id"],
                status=BackupStatus(r["status"]),
                size_bytes=r["size_bytes"], started_at=r["started_at"],
                completed_at=r["completed_at"],
                hostinger_backup_id=r["hostinger_backup_id"],
            )
            for r in rows
        ]

    async def record_completed(
        self,
        *,
        project_id: str,
        vps_resource_id: UUID,
        hostinger_backup_id: str,
        size_bytes: int,
        started_at: datetime,
        completed_at: datetime,
    ) -> UUID:
        """Notifie qu'un backup s'est termine (typiquement via webhook
        Hostinger ou job Arq).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO backups (
                    project_id, vps_resource_id, status, size_bytes,
                    started_at, completed_at, hostinger_backup_id
                ) VALUES ($1, $2, 'completed', $3, $4, $5, $6)
                RETURNING backup_id
                """,
                project_id, vps_resource_id, size_bytes,
                started_at, completed_at, hostinger_backup_id,
            )
        return row["backup_id"]

    async def restore(self, backup_id: UUID) -> BackupInfo:
        """Demande la restauration d'un backup."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE backups SET status = 'restoring', updated_at = NOW()
                 WHERE backup_id = $1 AND status = 'completed'
                RETURNING project_id, vps_resource_id, hostinger_backup_id
                """,
                backup_id,
            )
        if row is None:
            raise LookupError(
                f"backup {backup_id} introuvable ou non restaurable",
            )

        try:
            await self._client.request(
                "POST", f"/vps/backups/{row['hostinger_backup_id']}/restore",
            )
        except Exception:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE backups SET status = 'failed', updated_at = NOW()
                     WHERE backup_id = $1
                    """,
                    backup_id,
                )
            raise

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE backups SET status = 'restored', updated_at = NOW()
                 WHERE backup_id = $1
                """,
                backup_id,
            )

        logger.info(
            "backup.restored backup=%s vps=%s",
            backup_id, row["vps_resource_id"],
        )
        return BackupInfo(
            backup_id=backup_id, project_id=row["project_id"],
            vps_resource_id=row["vps_resource_id"],
            status=BackupStatus.RESTORED,
            size_bytes=None, started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            hostinger_backup_id=row["hostinger_backup_id"],
        )
