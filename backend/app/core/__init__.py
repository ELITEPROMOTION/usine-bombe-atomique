"""Core framework UBA V5.6 - domain-agnostic architecture.

Composants :
  - BaseDomain       : abstract class pour plugins metier
  - DomainRegistry   : registry thread-safe singleton
  - DomainContext    : contexte universel (tenant, user, correlation)
  - DomainRouter     : orchestrateur middleware chain
  - RulesEngine      : evaluation CEL + loader YAML
  - FeatureFlags     : evaluation hierarchique (user > tenant > %rollout > global)

Usage :
    from app.core import DomainRegistry, DomainContext
    registry = DomainRegistry.instance()
    domain = registry.get("fiscal_dz")
    ctx = DomainContext(tenant_id="x", user_id="y", domain_id="fiscal_dz")
    result = await domain.process(input_data, ctx)
"""
from app.core.domain_context import DomainContext
from app.core.domain_engine import BaseDomain, DomainRegistry, DomainRouter
from app.core.domain_results import Invariant, ProcessResult, Report, ValidationResult

__all__ = [
    "BaseDomain",
    "DomainContext",
    "DomainRegistry",
    "DomainRouter",
    "Invariant",
    "ProcessResult",
    "Report",
    "ValidationResult",
]
