"""SSLManager : Let's Encrypt via Hostinger.

Operations : `request_cert` (gratuit), `renew_cert`, `list_certs`.
Pas de payment_id requis (Let's Encrypt = gratuit).
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


class SSLCertStatus(str, enum.Enum):
    PENDING = "pending"
    ISSUED = "issued"
    RENEWING = "renewing"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass(frozen=True)
class SSLCertificate:
    cert_id: UUID
    domain: str
    project_id: str
    status: SSLCertStatus
    issued_at: datetime | None
    expires_at: datetime | None
    last_renewed_at: datetime | None


class SSLManager:
    def __init__(self, pool: asyncpg.Pool, client: Any) -> None:
        self._pool = pool
        self._client = client

    async def request_cert(
        self, *, project_id: str, domain: str,
    ) -> SSLCertificate:
        """Demande Let's Encrypt — gratuit, pas de gate payment_id."""
        if not domain or "." not in domain:
            raise ValueError("domain invalide")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ssl_certificates (project_id, domain, status)
                VALUES ($1, $2, 'pending')
                ON CONFLICT (project_id, domain) DO UPDATE
                   SET status = 'pending', updated_at = NOW()
                RETURNING cert_id
                """,
                project_id, domain.lower(),
            )
            cert_id: UUID = row["cert_id"]

        # Appel API : Let's Encrypt = gratuit donc require_live=False acceptable.
        # Mais en prod on garde le gate UBA_LIVE_HOSTINGER pour eviter les
        # appels accidentels lors de tests d'integration.
        try:
            result = await self._client.request(
                "POST", "/ssl/certificates",
                json_body={"domain": domain.lower(), "type": "letsencrypt"},
            )
        except Exception as exc:
            await self._mark_failed(cert_id, str(exc)[:500])
            raise

        body = result.json_body
        issued_iso = body.get("issued_at")
        expires_iso = body.get("expires_at")
        issued_at = datetime.fromisoformat(issued_iso) if issued_iso else None
        expires_at = datetime.fromisoformat(expires_iso) if expires_iso else None

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ssl_certificates
                   SET status = 'issued',
                       issued_at = $2, expires_at = $3,
                       updated_at = NOW(),
                       hostinger_metadata_json = $4::jsonb
                 WHERE cert_id = $1
                """,
                cert_id, issued_at, expires_at,
                json.dumps(body, sort_keys=True, ensure_ascii=False, default=str),
            )

        logger.info("ssl.requested project=%s domain=%s", project_id, domain)
        return SSLCertificate(
            cert_id=cert_id, domain=domain.lower(), project_id=project_id,
            status=SSLCertStatus.ISSUED, issued_at=issued_at,
            expires_at=expires_at, last_renewed_at=None,
        )

    async def renew_cert(self, cert_id: UUID) -> SSLCertificate:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE ssl_certificates
                   SET status = 'renewing', updated_at = NOW()
                 WHERE cert_id = $1 AND status IN ('issued','expired')
                RETURNING domain, project_id
                """,
                cert_id,
            )
        if row is None:
            raise LookupError(f"cert {cert_id} introuvable ou non renouvelable")

        try:
            result = await self._client.request(
                "POST", f"/ssl/certificates/{cert_id}/renew",
            )
        except Exception as exc:
            await self._mark_failed(cert_id, str(exc)[:500])
            raise

        body = result.json_body
        expires_iso = body.get("expires_at")
        expires_at = datetime.fromisoformat(expires_iso) if expires_iso else None
        now = datetime.now(UTC)

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ssl_certificates
                   SET status = 'issued', expires_at = $2,
                       last_renewed_at = NOW(), updated_at = NOW()
                 WHERE cert_id = $1
                """,
                cert_id, expires_at,
            )

        logger.info("ssl.renewed cert=%s domain=%s", cert_id, row["domain"])
        return SSLCertificate(
            cert_id=cert_id, domain=row["domain"], project_id=row["project_id"],
            status=SSLCertStatus.ISSUED, issued_at=None,
            expires_at=expires_at, last_renewed_at=now,
        )

    async def list_certs(self, project_id: str) -> list[SSLCertificate]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT cert_id, project_id, domain, status,
                       issued_at, expires_at, last_renewed_at
                  FROM ssl_certificates
                 WHERE project_id = $1
                 ORDER BY issued_at DESC NULLS LAST, cert_id
                """,
                project_id,
            )
        return [
            SSLCertificate(
                cert_id=r["cert_id"], domain=r["domain"],
                project_id=r["project_id"],
                status=SSLCertStatus(r["status"]),
                issued_at=r["issued_at"], expires_at=r["expires_at"],
                last_renewed_at=r["last_renewed_at"],
            )
            for r in rows
        ]

    async def _mark_failed(self, cert_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE ssl_certificates
                   SET status = 'failed', updated_at = NOW(),
                       hostinger_metadata_json = jsonb_build_object('error', $2::text)
                 WHERE cert_id = $1
                """,
                cert_id, reason,
            )
