"""Generateur de liens directs.

Emet des tokens cryptographiquement aleatoires (`secrets.token_urlsafe(32)`)
et persiste **uniquement le SHA-256** du token dans `direct_links`.
Le token brut quitte la fonction et n'est plus jamais stocke : si la base
fuit, les liens actifs ne sont pas exploitables.

L'audit (`direct_links_audit`) trace l'evenement `issued` pour chaque
emission.
"""
from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.direct_links.catalog import Catalog

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssuedLink:
    link_id: UUID
    token: str           # token brut a transmettre une seule fois (jamais persiste)
    url: str
    action_type: str
    target_id: str
    expires_at: datetime
    single_use: bool


def hash_token(token: str) -> str:
    """SHA-256 du token brut. Rendu public pour les tests et le validator."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _build_url(base_url: str, callback_path: str, token: str) -> str:
    base = base_url.rstrip("/")
    path = callback_path if callback_path.startswith("/") else "/" + callback_path
    return f"{base}{path}?t={token}"


class DirectLinkGenerator:
    """API d'emission de liens. Une instance partagee par requete/worker."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        catalog: Catalog,
        *,
        base_url: str = "https://app.uba.studio",
    ) -> None:
        self._pool = pool
        self._catalog = catalog
        self._base_url = base_url

    async def issue(
        self,
        *,
        action_type: str,
        target_id: str,
        principal_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl: timedelta | None = None,
    ) -> IssuedLink:
        entry = self._catalog.get(action_type)  # leve KeyError si inconnu

        token = _new_token()
        token_hash = hash_token(token)
        expires_at = datetime.now(UTC) + (
            ttl if ttl is not None else timedelta(seconds=entry.default_ttl_seconds)
        )
        url = _build_url(self._base_url, entry.callback_path, token)
        meta_json = json.dumps(metadata or {}, sort_keys=True, ensure_ascii=False, default=str)

        async with self._pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO direct_links (
                    token_hash, action_type, target_id, principal_id,
                    metadata_json, single_use, expires_at
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                RETURNING link_id
                """,
                token_hash,
                action_type,
                target_id,
                principal_id,
                meta_json,
                entry.single_use,
                expires_at,
            )
            link_id: UUID = row["link_id"]

            await conn.execute(
                """
                INSERT INTO direct_links_audit (link_id, event, detail_json)
                VALUES ($1, 'issued', $2::jsonb)
                """,
                link_id,
                json.dumps(
                    {
                        "action_type": action_type,
                        "target_id": target_id,
                        "principal_id": principal_id,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ),
            )

        # On loggue les meta techniques mais jamais le token brut.
        logger.info(
            "direct_link.issued action=%s target=%s link_id=%s ttl_s=%d",
            action_type,
            target_id,
            link_id,
            int((expires_at - datetime.now(UTC)).total_seconds()),
        )

        return IssuedLink(
            link_id=link_id,
            token=token,
            url=url,
            action_type=action_type,
            target_id=target_id,
            expires_at=expires_at,
            single_use=entry.single_use,
        )
