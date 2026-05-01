"""Espace client (`/api/v1/client/*`).

Auth : JWT client signe avec `JWT_CLIENT_SECRET` (ADR-33). Le claim
`project_id` scope tous les endpoints — un client ne peut acceder qu'au
project pour lequel son token est emis.

Endpoints :
- GET  /client/project
- GET  /client/milestones
- GET  /client/activity?limit=N
- GET  /client/deliverables
- GET  /client/deliverables/{token}/download   (302 redirect)
- GET  /client/invoices
- GET  /client/invoices/{token}/pdf            (302 redirect)
- GET  /client/handoffs
- GET  /client/profile
- PATCH /client/profile/consents
- POST /client/profile/gdpr/export
- POST /client/profile/gdpr/erasure
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Annotated, Final
from uuid import UUID

import asyncpg
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.database import get_pool
from app.saas_factory.client_area import (
    ClientDashboardService,
    ClientPaymentsService,
    ClientProfileService,
)
from app.saas_factory.client_area.dashboard_service import (
    ProjectNotFoundError,
)
from app.saas_factory.legal.gdpr_erasure import ErasureNotPermittedError
from app.security.jwt_client import (
    JWTClientConfigMissingError,
    JWTClientError,
    JWTClientPayload,
    is_jwt_client_mode_enabled,
    verify_client_token,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client", tags=["client"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------
def _strip_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


async def require_client_jwt(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> JWTClientPayload:
    """Verifie le JWT client. Fail-closed si la config manque."""
    if not is_jwt_client_mode_enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "JWT_CLIENT_SECRET non configure",
        )
    bearer = _strip_bearer(authorization)
    if not bearer:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Authorization Bearer requis",
        )
    try:
        payload = verify_client_token(bearer)
    except JWTClientConfigMissingError as exc:        # pragma: no cover
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, str(exc),
        ) from exc
    except JWTClientError as exc:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"JWT client invalide: {exc}",
        ) from exc
    return payload


PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
ClientPrincipal = Annotated[JWTClientPayload, Depends(require_client_jwt)]


# ---------------------------------------------------------------------------
# Schemas (alignes sur frontend client_fixtures.ts)
# ---------------------------------------------------------------------------
class ProjectOut(BaseModel):
    project_id: UUID
    pack_id: str
    pack_name: str
    status: str
    progress_pct: int = Field(ge=0, le=100)
    created_at: datetime
    estimated_delivery_at: datetime
    owner_email: str
    company_name: str
    next_milestone: str
    next_milestone_due_at: datetime


class MilestoneOut(BaseModel):
    id: str
    label: str
    description: str
    due_at: datetime
    status: str


class ActivityOut(BaseModel):
    id: str
    at: datetime
    kind: str
    title: str
    detail: str | None


class DeliverableOut(BaseModel):
    id: str
    name: str
    category: str
    size_bytes: int = Field(ge=0)
    released_at: datetime
    download_token: str
    preview_url: str | None


class InvoiceOut(BaseModel):
    invoice_id: UUID
    number: str
    amount_cents: int = Field(ge=0)
    currency: str
    status: str
    issued_at: datetime
    paid_at: datetime | None
    pdf_token: str


class HandoffOut(BaseModel):
    id: UUID
    action_type: str
    title: str
    description: str
    due_at: datetime
    status: str
    cta_label: str
    cta_url: str


class ProfileOut(BaseModel):
    owner_email: str
    company_name: str
    locale: str
    consent_marketing: bool
    consent_analytics: bool
    created_at: datetime


class ConsentsPatchIn(BaseModel):
    consent_marketing: bool
    consent_analytics: bool


class ErasureRequestIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class GDPRExportOut(BaseModel):
    request_id: str


class GDPRErasureOut(BaseModel):
    request_id: str
    executable_after: datetime


_CTA_HOST_PREFIX: Final[str] = "/client/handoffs/"
_N8N_GDPR_WEBHOOK_ENV: Final[str] = "N8N_GDPR_WEBHOOK_URL"


async def _fire_and_forget_gdpr_webhook(payload: dict) -> None:
    """POST asynchrone vers n8n workflow 03 (gdpr_request_notify).

    No-op silencieux si N8N_GDPR_WEBHOOK_URL non configure. Toute
    erreur est loggee mais n'affecte pas la reponse client.
    """
    url = os.environ.get(_N8N_GDPR_WEBHOOK_ENV, "").strip()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            await http.post(url, json=payload)
    except Exception as exc:
        logger.debug("n8n gdpr webhook failed: %s", exc)


def _emit_gdpr_webhook_bg(kind: str, payload: dict) -> None:
    """Schedule le webhook sans attendre (fire-and-forget intentionnel)."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(  # noqa: RUF006  -- fire-and-forget intentionnel
            _fire_and_forget_gdpr_webhook({"kind": kind, **payload}),
        )
    except RuntimeError:
        # pas de loop : ignore (e.g. test sync)
        pass


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.get("/project", response_model=ProjectOut)
async def get_project(
    principal: ClientPrincipal, pool: PoolDep,
) -> ProjectOut:
    svc = ClientDashboardService(pool)
    try:
        row = await svc.get_project(principal.project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProjectOut(**row.__dict__)


@router.get("/milestones", response_model=list[MilestoneOut])
async def list_milestones(
    principal: ClientPrincipal, pool: PoolDep,
) -> list[MilestoneOut]:
    svc = ClientDashboardService(pool)
    try:
        items = await svc.list_milestones(principal.project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return [MilestoneOut(**m.__dict__) for m in items]


@router.get("/activity", response_model=list[ActivityOut])
async def list_activity(
    principal: ClientPrincipal, pool: PoolDep, limit: int = 10,
) -> list[ActivityOut]:
    if limit < 1 or limit > 100:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "limit must be in [1..100]",
        )
    svc = ClientDashboardService(pool)
    items = await svc.list_activity(principal.project_id, limit=limit)
    return [ActivityOut(**a.__dict__) for a in items]


@router.get("/deliverables", response_model=list[DeliverableOut])
async def list_deliverables(
    principal: ClientPrincipal,
) -> list[DeliverableOut]:
    """Phase 9M-bis : la table `deliverables` n'existe pas encore en V9.

    On expose une liste **vide** ici plutot qu'une erreur — le frontend
    affichera l'etat "aucun livrable disponible". Branchement reel a
    faire en phase deliverables (post-V9 ou phase ulterieure).
    """
    return []


@router.get("/deliverables/{token}/download")
async def download_deliverable(
    token: str, principal: ClientPrincipal,
) -> RedirectResponse:
    """Stub : aucun deliverable cataloge actuellement. 404."""
    raise HTTPException(
        status.HTTP_404_NOT_FOUND,
        f"livrable {token!r} introuvable",
    )


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(
    principal: ClientPrincipal, pool: PoolDep,
) -> list[InvoiceOut]:
    svc = ClientPaymentsService(pool)
    items = await svc.list_invoices(principal.project_id)
    return [InvoiceOut(**i.__dict__) for i in items]


@router.get("/invoices/{token}/pdf")
async def get_invoice_pdf(
    token: str, principal: ClientPrincipal, pool: PoolDep,
) -> RedirectResponse:
    """Redirige vers `invoices.pdf_url` si dispo, sinon 404."""
    try:
        invoice_id = UUID(token)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "token de facture invalide",
        ) from exc
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT pdf_url, project_id FROM invoices
             WHERE invoice_id = $1
            """,
            invoice_id,
        )
    if row is None or row["project_id"] != str(principal.project_id):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "facture introuvable",
        )
    if not row["pdf_url"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "PDF de la facture pas encore genere",
        )
    return RedirectResponse(url=row["pdf_url"], status_code=302)


@router.get("/handoffs", response_model=list[HandoffOut])
async def list_handoffs(
    principal: ClientPrincipal, pool: PoolDep,
) -> list[HandoffOut]:
    svc = ClientPaymentsService(pool)
    items = await svc.list_handoffs(principal.project_id)
    return [HandoffOut(**h.__dict__) for h in items]


@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    principal: ClientPrincipal, pool: PoolDep,
) -> ProfileOut:
    svc = ClientProfileService(pool)
    try:
        row = await svc.get_profile(principal.project_id)
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProfileOut(**row.__dict__)


@router.patch("/profile/consents", response_model=ProfileOut)
async def update_consents(
    payload: ConsentsPatchIn,
    principal: ClientPrincipal, pool: PoolDep,
) -> ProfileOut:
    svc = ClientProfileService(pool)
    try:
        row = await svc.update_consents(
            principal.project_id,
            consent_marketing=payload.consent_marketing,
            consent_analytics=payload.consent_analytics,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return ProfileOut(**row.__dict__)


@router.post("/profile/gdpr/export", response_model=GDPRExportOut, status_code=202)
async def request_gdpr_export(
    principal: ClientPrincipal, pool: PoolDep,
) -> GDPRExportOut:
    svc = ClientProfileService(pool)
    try:
        out = await svc.request_export(
            principal.project_id, requester_email=principal.sub,
        )
    except ProjectNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    _emit_gdpr_webhook_bg("export", {
        "request_id": out["request_id"],
        "project_id": str(principal.project_id),
        "requester_email": principal.sub,
    })
    return GDPRExportOut(**out)


@router.post("/profile/gdpr/erasure", response_model=GDPRErasureOut, status_code=202)
async def request_gdpr_erasure(
    payload: ErasureRequestIn,
    principal: ClientPrincipal, pool: PoolDep,
) -> GDPRErasureOut:
    svc = ClientProfileService(pool)
    try:
        out = await svc.request_erasure(
            principal.project_id,
            reason=payload.reason,
            requester_email=principal.sub,
        )
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ErasureNotPermittedError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    _emit_gdpr_webhook_bg("erasure", {
        "request_id": out["request_id"],
        "executable_after": out["executable_after"],
        "project_id": str(principal.project_id),
        "requester_email": principal.sub,
    })
    return GDPRErasureOut(**out)
