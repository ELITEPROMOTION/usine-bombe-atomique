"""DomainContext : contexte universel propagé dans chaque operation domaine.

Equivalent conceptuel de context.Context (Go) + tracer baggage OpenTelemetry.
Utilise par BaseDomain.validate/process/report pour :
  - Isolation tenant (RLS + permissions)
  - Tracing correlation (log/metrics/audit)
  - Feature flags scoping (user > tenant > global)
  - Localisation (locale + timezone)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class DomainContext(BaseModel):
    """Contexte execution d'une operation domaine (immutable)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str = Field(..., description="UUID ou slug entite multi-tenant")
    user_id: str | None = Field(None, description="UUID user initiateur (None = system)")
    domain_id: str = Field(..., description="Identifiant du domaine ('fiscal_dz', etc.)")
    correlation_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="ID de correlation cross-system pour tracing distribue",
    )

    locale: str = Field(default="fr-DZ", description="BCP-47 tag")
    timezone_name: str = Field(default="Africa/Algiers", alias="timezone")

    permissions: frozenset[str] = Field(
        default_factory=frozenset,
        description="Permissions accordees (Zanzibar-style)",
    )
    feature_flags: dict[str, bool] = Field(
        default_factory=dict,
        description="Snapshot des flags pour cette operation",
    )

    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def with_flags(self, **flags: bool) -> "DomainContext":
        """Derive un nouveau context avec feature flags supplementaires."""
        return self.model_copy(
            update={"feature_flags": {**self.feature_flags, **flags}},
        )

    def has_permission(self, permission: str) -> bool:
        """Check permission Zanzibar-like (support wildcards)."""
        if permission in self.permissions:
            return True
        # Wildcards : 'domain:*' matches 'domain:read' etc.
        for p in self.permissions:
            if p.endswith("*") and permission.startswith(p[:-1]):
                return True
        return False

    def feature_enabled(self, flag: str, default: bool = False) -> bool:
        return self.feature_flags.get(flag, default)
