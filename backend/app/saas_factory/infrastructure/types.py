"""DTOs et enums pour les operations Hostinger."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class HostingerResourceType(str, enum.Enum):
    DOMAIN = "domain"
    VPS = "vps"
    SSL = "ssl"
    BACKUP = "backup"


class HostingerResourceStatus(str, enum.Enum):
    PENDING = "pending"           # cree en DB, pas encore live
    PROVISIONING = "provisioning" # appel API en cours
    ACTIVE = "active"             # operationnel
    FAILED = "failed"             # echec irrattrapable
    DESTROYED = "destroyed"       # detruit (volontairement)


# ---------------------------------------------------------------------------
# Domains
# ---------------------------------------------------------------------------
class DomainSearchResult(BaseModel):
    query: str
    available: bool
    price_eur: float | None = None
    suggested_alternatives: list[str] = Field(default_factory=list)
    tld: str
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tld")
    @classmethod
    def _normalize_tld(cls, v: str) -> str:
        return v.lower().lstrip(".")


# ---------------------------------------------------------------------------
# VPS
# ---------------------------------------------------------------------------
class VPSPlan(BaseModel):
    plan_id: str = Field(min_length=1, max_length=64)
    label: str
    cpu_cores: int = Field(ge=1, le=64)
    ram_gb: int = Field(ge=1, le=512)
    disk_gb: int = Field(ge=10, le=10000)
    monthly_price_eur: float = Field(ge=0.0)


class VPSCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    plan_id: str = Field(min_length=1, max_length=64)
    region: str = Field(min_length=2, max_length=32)
    hostname: str = Field(pattern=r"^[a-z0-9-]+$", min_length=3, max_length=63)
    payment_id: str = Field(min_length=8, max_length=120)
    ssh_keys: list[str] = Field(default_factory=list, max_length=10)


class VPSInstance(BaseModel):
    instance_id: str
    plan_id: str
    region: str
    hostname: str
    status: HostingerResourceStatus
    ipv4: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Resource record (DB)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HostingerResource:
    resource_id: str        # notre UUID interne
    resource_type: HostingerResourceType
    project_id: str
    hostinger_id: str | None  # id chez Hostinger (apres creation)
    status: HostingerResourceStatus
    payment_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
