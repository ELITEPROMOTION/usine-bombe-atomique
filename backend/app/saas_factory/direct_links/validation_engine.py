"""Moteur de validation / consommation / revocation des liens directs.

Securite :
- Le token recu n'est jamais persiste : on hash en SHA-256 et on cherche
  le hash dans `direct_links`.
- `consume()` est atomique (UPDATE conditionnel WHERE consumed_at IS NULL)
  pour eviter la double-consommation en cas de double-clic.
- Toute decision est tracee dans `direct_links_audit` avec un evenement
  parmi : viewed, consumed, expired, revoked, invalid_token.
- L'IP est hashee (SHA-256) avant stockage pour ne pas violer la RGPD.

Limitations connues :
- Pas de rate-limit ici : c'est le role d'un middleware FastAPI / nginx.
- Pas de detection de bruteforce : combinable avec un compteur Redis dans
  une phase ulterieure.
"""
from __future__ import annotations

import enum
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.direct_links.catalog import Catalog
from app.saas_factory.direct_links.direct_link_generator import hash_token

logger = logging.getLogger(__name__)


class LinkStatus(str, enum.Enum):
    VALID = "valid"
    EXPIRED = "expired"
    CONSUMED = "consumed"
    REVOKED = "revoked"
    UNKNOWN = "unknown"      # token jamais emis ou mal forme


@dataclass(frozen=True)
class LinkResolution:
    status: LinkStatus
    link_id: UUID | None
    action_type: str | None
    target_id: str | None
    principal_id: str | None
    metadata: dict[str, Any]
    expires_at: datetime | None
    single_use: bool

    @property
    def is_valid(self) -> bool:
        return self.status is LinkStatus.VALID


def _hash_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _row_to_resolution(row: asyncpg.Record, *, status: LinkStatus) -> LinkResolution:
    meta = row["metadata_json"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    return LinkResolution(
        status=status,
        link_id=row["link_id"],
        action_type=row["action_type"],
        target_id=row["target_id"],
        principal_id=row["principal_id"],
        metadata=meta or {},
        expires_at=row["expires_at"],
        single_use=row["single_use"],
    )


_UNKNOWN = LinkResolution(
    status=LinkStatus.UNKNOWN,
    link_id=None,
    action_type=None,
    target_id=None,
    principal_id=None,
    metadata={},
    expires_at=None,
    single_use=False,
)


class ValidationEngine:
    def __init__(self, pool: asyncpg.Pool, catalog: Catalog) -> None:
        self._pool = pool
        self._catalog = catalog

    async def _audit(
        self,
        conn: asyncpg.Connection,
        *,
        link_id: UUID | None,
        event: str,
        user_agent: str | None,
        ip: str | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        await conn.execute(
            """
            INSERT INTO direct_links_audit
                (link_id, event, user_agent, ip_hash, detail_json)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            """,
            link_id,
            event[:32],
            (user_agent or "")[:512] or None,
            _hash_ip(ip),
            json.dumps(detail or {}, sort_keys=True, ensure_ascii=False, default=str),
        )

    async def validate(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> LinkResolution:
        if not token or len(token) < 16:
            # Token vide ou trop court : on n'audite meme pas (eviterait du
            # bruit en cas de scan). Mais pour la tracabilite on logue.
            logger.info("direct_link.validate ignored (malformed token)")
            return _UNKNOWN

        token_hash = hash_token(token)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT link_id, action_type, target_id, principal_id,
                       metadata_json, single_use, expires_at,
                       consumed_at, revoked_at
                  FROM direct_links
                 WHERE token_hash = $1
                """,
                token_hash,
            )
            if row is None:
                await self._audit(
                    conn,
                    link_id=None,
                    event="invalid_token",
                    user_agent=user_agent,
                    ip=ip,
                )
                return _UNKNOWN

            now = datetime.now(UTC)
            if row["revoked_at"] is not None:
                status = LinkStatus.REVOKED
            elif row["consumed_at"] is not None:
                status = LinkStatus.CONSUMED
            elif row["expires_at"] <= now:
                status = LinkStatus.EXPIRED
            else:
                status = LinkStatus.VALID

            await self._audit(
                conn,
                link_id=row["link_id"],
                event="viewed" if status is LinkStatus.VALID else status.value,
                user_agent=user_agent,
                ip=ip,
            )
            return _row_to_resolution(row, status=status)

    async def consume(
        self,
        token: str,
        *,
        user_agent: str | None = None,
        ip: str | None = None,
    ) -> LinkResolution:
        """Marque un lien single-use comme consomme. Atomique."""
        if not token or len(token) < 16:
            return _UNKNOWN
        token_hash = hash_token(token)
        async with self._pool.acquire() as conn, conn.transaction():
            # On verrouille la ligne et on consomme conditionnellement.
            row = await conn.fetchrow(
                """
                UPDATE direct_links
                   SET consumed_at = NOW()
                 WHERE token_hash = $1
                   AND single_use = TRUE
                   AND consumed_at IS NULL
                   AND revoked_at IS NULL
                   AND expires_at > NOW()
                RETURNING link_id, action_type, target_id, principal_id,
                          metadata_json, single_use, expires_at
                """,
                token_hash,
            )
            if row is None:
                # Soit le token est inconnu, soit deja consomme/revoque/expire/non-single-use.
                # On retourne le verdict via une lecture simple.
                resolution = await self.validate(token, user_agent=user_agent, ip=ip)
                return resolution

            await self._audit(
                conn,
                link_id=row["link_id"],
                event="consumed",
                user_agent=user_agent,
                ip=ip,
            )
            return _row_to_resolution(row, status=LinkStatus.CONSUMED)

    async def revoke(
        self,
        link_id: UUID,
        *,
        reason: str,
        actor: str = "system",
    ) -> bool:
        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                UPDATE direct_links
                   SET revoked_at = NOW(),
                       revocation_reason = $2
                 WHERE link_id = $1
                   AND revoked_at IS NULL
                RETURNING link_id
                """,
                link_id,
                reason[:500],
            )
            if row is None:
                return False
            await self._audit(
                conn,
                link_id=link_id,
                event="revoked",
                user_agent=None,
                ip=None,
                detail={"reason": reason[:500], "actor": actor[:64]},
            )
            return True
