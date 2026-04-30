"""DomainManager : recherche libre + achat gated par payment_id.

Recherche (`search`, `check_availability`) = lecture seule, gratuit.
Achat (`purchase`) = facturable, exige `payment_id` valide ET le mode
live (UBA_LIVE_HOSTINGER=1).

Toutes les operations sont auditees dans `hostinger_audit`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel, Field, field_validator

from app.saas_factory.infrastructure.hostinger_client import (
    HostingerCallResult,
    require_payment_id,
)
from app.saas_factory.infrastructure.types import (
    DomainSearchResult,
    HostingerResourceStatus,
)

logger = logging.getLogger(__name__)


class DomainPurchaseRequest(BaseModel):
    project_id: str = Field(min_length=1)
    domain: str = Field(
        pattern=r"^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$",
        min_length=4, max_length=253,
    )
    years: int = Field(ge=1, le=10)
    payment_id: str = Field(min_length=8, max_length=120)
    privacy_protection: bool = True
    auto_renew: bool = True

    @field_validator("domain")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


@dataclass(frozen=True)
class DomainPurchaseRecord:
    resource_id: UUID
    project_id: str
    domain: str
    payment_id: str
    status: HostingerResourceStatus
    hostinger_id: str | None
    expires_at: datetime | None
    created_at: datetime


class DomainManager:
    def __init__(
        self,
        pool: asyncpg.Pool,
        client: Any,            # HostingerClient ou StubHostingerClient
    ) -> None:
        self._pool = pool
        self._client = client

    async def search(self, query: str) -> DomainSearchResult:
        """Recherche libre — pas facturable, pas de garde live."""
        if not query or "." not in query:
            raise ValueError("query doit contenir un TLD (ex. 'mybusiness.fr')")
        path = "/domains/check"
        # require_live=False pour autoriser le stub a fonctionner sans gate
        result: HostingerCallResult = await self._client.request(
            "GET", path, params={"domain": query}, require_live=False,
        )
        body = result.json_body
        tld = query.rsplit(".", 1)[-1]
        await self._record_search(
            query=query, available=bool(body.get("available", False)),
            raw=body,
        )
        return DomainSearchResult(
            query=query.lower(),
            available=bool(body.get("available", False)),
            price_eur=float(body["price_eur"]) if body.get("price_eur") else None,
            suggested_alternatives=list(body.get("suggested", []) or []),
            tld=tld,
            raw=body,
        )

    async def check_availability(self, domain: str) -> bool:
        """Variante condensee de search() : retourne juste un bool."""
        return (await self.search(domain)).available

    async def purchase(self, req: DomainPurchaseRequest) -> DomainPurchaseRecord:
        """Achat domaine — GATED par payment_id ET UBA_LIVE_HOSTINGER=1."""
        # Garde-fou applicatif AVANT tout appel reseau.
        require_payment_id("domain.purchase", req.payment_id)

        # 1. Cree la resource en DB (status=provisioning) AVANT l'appel API
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO hostinger_resources (
                    resource_type, project_id, status, payment_id, metadata_json
                ) VALUES ('domain', $1, 'provisioning', $2, $3::jsonb)
                RETURNING resource_id, created_at
                """,
                req.project_id, req.payment_id,
                json.dumps({
                    "domain": req.domain, "years": req.years,
                    "privacy_protection": req.privacy_protection,
                    "auto_renew": req.auto_renew,
                }, sort_keys=True, ensure_ascii=False, default=str),
            )
            resource_id: UUID = row["resource_id"]
            created_at: datetime = row["created_at"]

        await self._audit(
            resource_id=resource_id,
            event="purchase_requested",
            payload={"domain": req.domain, "years": req.years},
        )

        # 2. Appel API : require_live=True par defaut -> bloque si gate fermee
        try:
            result = await self._client.request(
                "POST", "/domains/purchase",
                json_body={
                    "domain": req.domain,
                    "years": req.years,
                    "payment_reference": req.payment_id,
                    "privacy_protection": req.privacy_protection,
                    "auto_renew": req.auto_renew,
                },
            )
        except Exception as exc:
            await self._mark_failed(resource_id, str(exc)[:500])
            await self._audit(
                resource_id=resource_id, event="purchase_failed",
                payload={"error": str(exc)[:500]},
            )
            raise

        body = result.json_body
        hostinger_id = str(body.get("domain_id") or body.get("id") or "")
        expires_iso = body.get("expires_at")
        expires_at = datetime.fromisoformat(expires_iso) if expires_iso else None

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE hostinger_resources
                   SET hostinger_id = $2,
                       status = 'active',
                       updated_at = NOW(),
                       metadata_json = metadata_json || $3::jsonb
                 WHERE resource_id = $1
                """,
                resource_id, hostinger_id,
                json.dumps({
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "raw": body,
                }, sort_keys=True, ensure_ascii=False, default=str),
            )

        await self._audit(
            resource_id=resource_id, event="purchase_succeeded",
            payload={"hostinger_id": hostinger_id,
                     "expires_at": expires_at.isoformat() if expires_at else None},
        )

        logger.info(
            "domain.purchased project=%s domain=%s hostinger_id=%s",
            req.project_id, req.domain, hostinger_id,
        )
        return DomainPurchaseRecord(
            resource_id=resource_id,
            project_id=req.project_id,
            domain=req.domain,
            payment_id=req.payment_id,
            status=HostingerResourceStatus.ACTIVE,
            hostinger_id=hostinger_id or None,
            expires_at=expires_at,
            created_at=created_at,
        )

    # --- internals ---
    async def _record_search(
        self, *, query: str, available: bool, raw: dict[str, Any],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO domain_searches (query, available, raw_json)
                VALUES ($1, $2, $3::jsonb)
                """,
                query.lower(), available,
                json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str),
            )

    async def _mark_failed(self, resource_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE hostinger_resources
                   SET status = 'failed',
                       updated_at = NOW(),
                       metadata_json = metadata_json || jsonb_build_object('error', $2::text)
                 WHERE resource_id = $1
                """,
                resource_id, reason,
            )

    async def _audit(
        self,
        *,
        resource_id: UUID,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hostinger_audit (resource_id, event, payload_json, occurred_at)
                VALUES ($1, $2, $3::jsonb, $4)
                """,
                resource_id, event[:64],
                json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str),
                datetime.now(UTC),
            )
