"""VPSProvisioner : list_plans libre, create_instance gated par payment_id."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.saas_factory.infrastructure.hostinger_client import (
    HostingerCallResult,
    require_payment_id,
)
from app.saas_factory.infrastructure.types import (
    HostingerResourceStatus,
    VPSCreateRequest,
    VPSInstance,
    VPSPlan,
)

logger = logging.getLogger(__name__)


class VPSProvisioner:
    def __init__(self, pool: asyncpg.Pool, client: Any) -> None:
        self._pool = pool
        self._client = client

    async def list_plans(self) -> list[VPSPlan]:
        """Plans VPS — lecture seule, libre."""
        result: HostingerCallResult = await self._client.request(
            "GET", "/vps/plans", require_live=False,
        )
        items = result.json_body.get("items", []) or result.json_body.get("plans", [])
        return [VPSPlan.model_validate(p) for p in items]

    async def create_instance(self, req: VPSCreateRequest) -> VPSInstance:
        """Provisioning VPS — GATED par payment_id (validation Pydantic)
        + UBA_LIVE_HOSTINGER=1 (cote client).
        """
        # Pydantic a deja valide payment_id min_length=8 — on double-check
        # via require_payment_id pour le message d'erreur explicite.
        require_payment_id("vps.create_instance", req.payment_id)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO hostinger_resources (
                    resource_type, project_id, status, payment_id, metadata_json
                ) VALUES ('vps', $1, 'provisioning', $2, $3::jsonb)
                RETURNING resource_id, created_at
                """,
                req.project_id, req.payment_id,
                json.dumps(req.model_dump(mode="json"), sort_keys=True,
                           ensure_ascii=False, default=str),
            )
            resource_id: UUID = row["resource_id"]
            created_at: datetime = row["created_at"]

        await self._audit(
            resource_id=resource_id, event="vps_create_requested",
            payload={"plan_id": req.plan_id, "region": req.region,
                     "hostname": req.hostname},
        )

        try:
            result = await self._client.request(
                "POST", "/vps/instances",
                json_body={
                    "plan_id": req.plan_id, "region": req.region,
                    "hostname": req.hostname, "ssh_keys": req.ssh_keys,
                    "payment_reference": req.payment_id,
                },
            )
        except Exception as exc:
            await self._mark_failed(resource_id, str(exc)[:500])
            await self._audit(
                resource_id=resource_id, event="vps_create_failed",
                payload={"error": str(exc)[:500]},
            )
            raise

        body = result.json_body
        instance_id = str(body.get("instance_id") or body.get("id") or "")
        ipv4 = body.get("ipv4") or body.get("ip_address")

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE hostinger_resources
                   SET hostinger_id = $2, status = 'active',
                       updated_at = NOW(),
                       metadata_json = metadata_json || $3::jsonb
                 WHERE resource_id = $1
                """,
                resource_id, instance_id,
                json.dumps({"ipv4": ipv4, "raw": body},
                           sort_keys=True, ensure_ascii=False, default=str),
            )

        await self._audit(
            resource_id=resource_id, event="vps_create_succeeded",
            payload={"instance_id": instance_id, "ipv4": ipv4},
        )

        logger.info(
            "vps.created project=%s instance=%s ipv4=%s",
            req.project_id, instance_id, ipv4 or "?",
        )
        return VPSInstance(
            instance_id=instance_id,
            plan_id=req.plan_id,
            region=req.region,
            hostname=req.hostname,
            status=HostingerResourceStatus.ACTIVE,
            ipv4=ipv4,
            created_at=created_at,
        )

    async def status(self, resource_id: UUID) -> dict[str, Any]:
        """Lit le statut d'une resource VPS depuis l'API Hostinger."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT hostinger_id, status FROM hostinger_resources
                 WHERE resource_id = $1 AND resource_type = 'vps'
                """,
                resource_id,
            )
        if row is None:
            raise LookupError(f"vps {resource_id} introuvable")
        if not row["hostinger_id"]:
            return {"local_status": row["status"], "remote": None}
        result = await self._client.request(
            "GET", f"/vps/instances/{row['hostinger_id']}", require_live=False,
        )
        return {"local_status": row["status"], "remote": result.json_body}

    async def destroy(self, resource_id: UUID, *, reason: str) -> bool:
        """Detruit un VPS. Pas facturable mais irreversible."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT hostinger_id, status FROM hostinger_resources
                 WHERE resource_id = $1 AND resource_type = 'vps'
                   AND status NOT IN ('destroyed','failed')
                """,
                resource_id,
            )
        if row is None:
            return False
        hostinger_id = row["hostinger_id"]

        await self._audit(
            resource_id=resource_id, event="vps_destroy_requested",
            payload={"reason": reason[:500]},
        )

        if hostinger_id:
            try:
                await self._client.request(
                    "DELETE", f"/vps/instances/{hostinger_id}",
                )
            except Exception as exc:
                await self._audit(
                    resource_id=resource_id, event="vps_destroy_failed",
                    payload={"error": str(exc)[:500]},
                )
                raise

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE hostinger_resources
                   SET status = 'destroyed', updated_at = NOW()
                 WHERE resource_id = $1
                """,
                resource_id,
            )
        await self._audit(
            resource_id=resource_id, event="vps_destroyed", payload={},
        )
        return True

    # --- internals ---
    async def _mark_failed(self, resource_id: UUID, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE hostinger_resources
                   SET status = 'failed', updated_at = NOW(),
                       metadata_json = metadata_json || jsonb_build_object('error', $2::text)
                 WHERE resource_id = $1
                """,
                resource_id, reason,
            )

    async def _audit(
        self, *, resource_id: UUID, event: str, payload: dict[str, Any],
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
