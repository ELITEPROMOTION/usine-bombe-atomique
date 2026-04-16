"""Schemas Pydantic v2 - contrats API."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


TaskStatus = Literal[
    "pending", "analyzing", "planning", "distributing",
    "executing", "validating", "reworking",
    "completed", "failed", "cancelled",
]
AgentStatus = Literal["pending", "running", "success", "failed", "timeout", "skipped"]
Verdict = Literal["PASS", "CONDITIONAL_PASS", "SOFT_FAIL", "HARD_FAIL"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    db: bool
    redis: bool


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)


class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TaskCreate(BaseModel):
    session_id: UUID | None = None
    prompt: str = Field(min_length=1, max_length=10_000)
    priority: Literal["low", "medium", "high", "critical"] = "high"


class TaskOut(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    prompt: str
    status: TaskStatus
    priority: str
    validation_score: float
    rework_count: int
    created_at: datetime
    updated_at: datetime


class AgentExecutionOut(BaseModel):
    id: UUID
    agent_id: str
    agent_name: str
    status: AgentStatus
    duration_ms: float | None
    output_json: dict[str, Any] | None
    created_at: datetime


class ValidationLogOut(BaseModel):
    level_number: int
    level_name: str
    score: float
    passed: bool
    details: str | None
