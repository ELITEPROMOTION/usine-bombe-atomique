"""Resultats standardises retournes par les domaines.

ValidationResult : sortie de BaseDomain.validate() -> valide | invalid + issues
ProcessResult    : sortie de BaseDomain.process()  -> output + audit trail
Report           : sortie de BaseDomain.report()   -> format export (JSON/CSV/PDF)
Invariant        : regle invariante du domaine (verifiable runtime)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Severity = Literal["info", "warning", "error", "critical"]


class Issue(BaseModel):
    """Probleme detecte pendant validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(..., description="Code normalise, ex: 'FISCAL_DZ_IRG_INVALID_BRACKET'")
    severity: Severity = "error"
    message: str
    path: str | None = Field(None, description="JSONPath sur l'input")
    context: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    """Resultat validation domaine."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    domain_id: str
    domain_version: str
    issues: list[Issue] = Field(default_factory=list)
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity in ("error", "critical"))

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity in ("error", "critical")]


class ProcessResult(BaseModel):
    """Resultat operation process() - output + audit."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    domain_id: str
    operation: str = Field(..., description="Verbe metier, ex: 'calculate_irg'")
    output: dict[str, Any] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    correlation_id: str
    duration_ms: int = 0
    rules_applied: list[str] = Field(default_factory=list)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class Report(BaseModel):
    """Sortie report() - format export normalise."""

    model_config = ConfigDict(extra="forbid")

    domain_id: str
    report_type: str = Field(..., description="'summary', 'declaration', 'bilan', etc.")
    format: Literal["json", "csv", "pdf", "xlsx", "html"] = "json"
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    content: dict[str, Any] | str | bytes
    metadata: dict[str, Any] = Field(default_factory=dict)


class Invariant(BaseModel):
    """Regle invariante verifiable (Property-based)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    invariant_id: str
    description: str
    domain_id: str
    severity: Severity = "error"
    check_expression: str = Field(..., description="Expression CEL ou Python lambda")
    examples_valid: list[dict[str, Any]] = Field(default_factory=list)
    examples_invalid: list[dict[str, Any]] = Field(default_factory=list)
