"""Base class partagee par les 5 domaines avec integration RulesEngine."""
from __future__ import annotations

from typing import Any, ClassVar

from app.core import BaseDomain, DomainContext, ProcessResult, ValidationResult
from app.core.domain_results import Issue
from app.core.rules_engine import RulesEngine


class RulesBasedDomain(BaseDomain):
    """BaseDomain qui delegue a RulesEngine pour validate/process."""

    # Subclasses override :
    domain_id: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = ""
    required_fields: ClassVar[tuple[str, ...]] = ()

    def __init__(self, rules_engine: RulesEngine) -> None:
        super().__init__()
        self.rules_engine = rules_engine

    async def validate(
        self, input_data: dict[str, Any], ctx: DomainContext,
    ) -> ValidationResult:
        issues: list[Issue] = []
        # Required fields
        for f in self.required_fields:
            if f not in input_data:
                issues.append(Issue(
                    code=f"{self.domain_id.upper()}_MISSING_FIELD",
                    severity="error",
                    message=f"Required field missing: {f}",
                    path=f,
                ))
        # Regles de validation (expression 'validate' dans le YAML)
        for rule in self.rules_engine.get_rules(self.domain_id):
            if not rule.enabled or rule.validate_expr is None:
                continue
            try:
                if rule.when and not self.rules_engine.evaluator.evaluate(
                    rule.when, {"input": input_data},
                ):
                    continue
                ok = bool(self.rules_engine.evaluator.evaluate(
                    rule.validate_expr, {"input": input_data},
                ))
                if not ok:
                    issues.append(Issue(
                        code=f"{self.domain_id.upper()}_RULE_FAIL_{rule.id}",
                        severity="error",
                        message=f"Rule violated: {rule.description or rule.id}",
                    ))
            except Exception as exc:
                issues.append(Issue(
                    code=f"{self.domain_id.upper()}_RULE_EVAL_ERROR",
                    severity="warning",
                    message=f"Rule {rule.id} eval error: {exc}",
                ))
        return ValidationResult(
            valid=all(i.severity not in ("error", "critical") for i in issues),
            domain_id=self.domain_id,
            domain_version=self.version,
            issues=issues,
        )

    async def process(
        self, input_data: dict[str, Any], ctx: DomainContext,
    ) -> ProcessResult:
        # 1. Validation prealable
        validation = await self.validate(input_data, ctx)
        if not validation.valid:
            return ProcessResult(
                success=False,
                domain_id=self.domain_id,
                operation="process",
                issues=validation.issues,
                correlation_id=ctx.correlation_id,
            )
        # 2. Evaluation rules
        output = self.rules_engine.evaluate(
            self.domain_id, {"input": input_data},
        )
        applied = output.pop("_rules_applied", [])
        return ProcessResult(
            success=True,
            domain_id=self.domain_id,
            operation="process",
            output=output,
            correlation_id=ctx.correlation_id,
            rules_applied=applied,
        )
