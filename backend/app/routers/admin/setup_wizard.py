"""Endpoints /admin/setup-wizard/* : full CRUD pour le WizardEngine 9B."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError

from app.database import get_pool
from app.routers.admin._schemas import WizardStateResponse
from app.routers.admin.dependencies import (
    AdminPrincipal,
    get_current_admin,
)
from app.saas_factory.setup_wizard.steps import StepKey
from app.saas_factory.setup_wizard.wizard_engine import (
    WizardEngine,
    WizardNotReadyError,
)

router = APIRouter(prefix="/admin/setup-wizard", tags=["admin-setup-wizard"])

PoolDep = Annotated[asyncpg.Pool, Depends(get_pool)]
AdminDep = Annotated[AdminPrincipal, Depends(get_current_admin)]


def _to_response(state: Any) -> WizardStateResponse:
    return WizardStateResponse(
        wizard_id=state.wizard_id,
        current_step=state.current_step.value,
        completed_steps=[s.value for s in state.completed_steps],
        status=state.status.value,
        started_at=state.started_at,
        committed_at=state.committed_at,
    )


@router.post("/start", response_model=WizardStateResponse, status_code=201)
async def start(admin: AdminDep, pool: PoolDep) -> WizardStateResponse:
    state = await WizardEngine(pool).start(started_by=admin.admin_id)
    return _to_response(state)


@router.get("/{wizard_id}", response_model=WizardStateResponse)
async def get_state(
    wizard_id: UUID, _admin: AdminDep, pool: PoolDep,
) -> WizardStateResponse:
    state = await WizardEngine(pool).get_state(wizard_id)
    if state is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"wizard {wizard_id} introuvable",
        )
    return _to_response(state)


@router.post(
    "/{wizard_id}/step/{step_key}",
    response_model=WizardStateResponse,
)
async def save_step(
    wizard_id: UUID,
    step_key: str,
    payload: dict[str, Any],
    _admin: AdminDep,
    pool: PoolDep,
) -> WizardStateResponse:
    try:
        step = StepKey(step_key)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"step_key invalide: {step_key}",
        ) from exc
    try:
        state = await WizardEngine(pool).save_step(wizard_id, step, payload)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, str(exc),
        ) from exc
    return _to_response(state)


@router.post("/{wizard_id}/commit", response_model=WizardStateResponse)
async def commit_wizard(
    wizard_id: UUID, admin: AdminDep, pool: PoolDep,
) -> WizardStateResponse:
    try:
        await WizardEngine(pool).commit(wizard_id, committed_by=admin.admin_id)
    except WizardNotReadyError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, str(exc),
        ) from exc
    except LookupError as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, str(exc),
        ) from exc
    state = await WizardEngine(pool).get_state(wizard_id)
    if state is None:                                       # pragma: no cover
        # Defense en profondeur : impossible si commit/abandon a juste reussi.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "wizard state disparu apres mutation",
        )
    return _to_response(state)


@router.post("/{wizard_id}/abandon", response_model=WizardStateResponse)
async def abandon(
    wizard_id: UUID, _admin: AdminDep, pool: PoolDep,
    reason: str = "admin abandon",
) -> WizardStateResponse:
    ok = await WizardEngine(pool).abandon(wizard_id, reason=reason)
    if not ok:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "wizard introuvable ou deja terminal",
        )
    state = await WizardEngine(pool).get_state(wizard_id)
    if state is None:                                       # pragma: no cover
        # Defense en profondeur : impossible si commit/abandon a juste reussi.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "wizard state disparu apres mutation",
        )
    return _to_response(state)
