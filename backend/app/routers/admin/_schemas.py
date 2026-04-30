"""Schemas Pydantic pour les routers /admin/*."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class HealthOk(BaseModel):
    ok: bool = True


class AuditedActionResponse(BaseModel):
    """Reponse standard pour toute action override."""
    action_id: UUID
    target_type: str
    target_id: str | None
    timestamp: datetime


# --- AI ---
class AIDecisionListItem(BaseModel):
    decision_id: UUID
    project_id: str
    requested_provider: str
    actual_provider: str
    status: str
    cost_usd: float
    tokens_in: int
    tokens_out: int
    latency_ms: int
    fallback_used: bool
    retries: int
    loop_detected: bool
    created_at: datetime


class AICostDashboardItem(BaseModel):
    project_id: str
    calls: int
    total_cost_usd: float
    tokens_in: int
    tokens_out: int
    fallbacks: int
    loops: int
    errors: int


class AIRouterPolicy(BaseModel):
    weights: dict[str, int]
    fallback_order: list[str]
    allow_fallback: bool = True
    max_attempts_per_provider: int = 3
    base_delay_s: float = 0.5


class AIRouterPolicyOverride(BaseModel):
    weights: dict[str, int] = Field(min_length=1)
    fallback_order: list[str] | None = None
    allow_fallback: bool | None = None
    max_attempts_per_provider: int | None = Field(default=None, ge=1, le=10)


# --- Handoffs ---
class HandoffListItem(BaseModel):
    handoff_id: UUID
    project_id: str
    action_type: str
    state: str
    target_email: str
    title: str
    expires_at: datetime
    created_at: datetime


class HandoffOverrideRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


# --- Projects ---
class ProjectListItem(BaseModel):
    project_id: UUID
    owner_email: str
    company_name: str
    pack_id_hint: str
    title: str
    status: str
    created_at: datetime


class ProjectStatusOverride(BaseModel):
    new_status: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


# --- Direct links ---
class DirectLinkListItem(BaseModel):
    link_id: UUID
    action_type: str
    target_id: str
    principal_id: str | None
    single_use: bool
    consumed_at: datetime | None
    revoked_at: datetime | None
    expires_at: datetime
    created_at: datetime


# --- Setup wizard ---
class WizardStateResponse(BaseModel):
    wizard_id: UUID
    current_step: str
    completed_steps: list[str]
    status: str
    started_at: datetime
    committed_at: datetime | None


# --- Onboarding ---
class OnboardingFunnelItem(BaseModel):
    current_step: str
    in_progress: int
    abandoned: int
    submitted: int


class OnboardingSessionListItem(BaseModel):
    session_id: UUID
    current_step: str
    status: str
    owner_email: str | None
    project_id: UUID | None
    started_at: datetime
    submitted_at: datetime | None


__all__ = [
    "AIDecisionListItem",
    "AICostDashboardItem",
    "AIRouterPolicy",
    "AIRouterPolicyOverride",
    "AuditedActionResponse",
    "DirectLinkListItem",
    "HandoffListItem",
    "HandoffOverrideRequest",
    "HealthOk",
    "OnboardingFunnelItem",
    "OnboardingSessionListItem",
    "ProjectListItem",
    "ProjectStatusOverride",
    "WizardStateResponse",
]


def asdict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")
