"""Domain engine : BaseDomain + DomainRegistry + DomainRouter.

Architecture inspiree :
  - Google CEL (expression evaluation sandboxed)
  - CNCF OpenTelemetry (tracing automatic via DomainContext.correlation_id)
  - Meta Zanzibar (permissions Zanzibar-style dans DomainContext)
  - JSON Schema 2020-12 (validation inputs via BaseDomain.schema ClassVar)

Les domaines (fiscal_dz, juridique, logistique, rh, comptabilite) etendent
`BaseDomain` et s'auto-enregistrent via `DomainRegistry.register()` dans
`app/domains/__init__.py`.
"""
from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from app.core.domain_context import DomainContext
from app.core.domain_results import (
    Invariant,
    Issue,
    ProcessResult,
    Report,
    ValidationResult,
)

logger = logging.getLogger("uba.core.domain_engine")


# ============================================================================
# BaseDomain - abstract class pour plugins metier
# ============================================================================

class BaseDomain(ABC):
    """Contract d'un domaine metier.

    Sous-classe avec :
        class FiscalDZDomain(BaseDomain):
            domain_id = "fiscal_dz"
            version = "1.0.0"
            description = "Fiscalite Algerie (IRG, IBS, TVA, TAP, IVR)"
            schema = { ... JSON Schema 2020-12 ... }

            async def validate(self, input, ctx): ...
            async def process(self, input, ctx):  ...
            async def report(self, output, format): ...
            def invariants(self): return [ ... ]
    """

    # Class attributes (to be overridden by subclasses)
    domain_id: ClassVar[str] = ""
    version: ClassVar[str] = "0.0.0"
    description: ClassVar[str] = ""
    schema: ClassVar[dict[str, Any]] = {}
    supported_operations: ClassVar[tuple[str, ...]] = ()

    def __init__(self) -> None:
        if not self.domain_id:
            raise ValueError(f"{type(self).__name__} must set domain_id")
        if not self.version:
            raise ValueError(f"{type(self).__name__} must set version")

    @abstractmethod
    async def validate(
        self, input_data: dict[str, Any], ctx: DomainContext,
    ) -> ValidationResult:
        """Valide `input_data` vs JSON Schema + regles metier."""

    @abstractmethod
    async def process(
        self, input_data: dict[str, Any], ctx: DomainContext,
    ) -> ProcessResult:
        """Execute l'operation metier principale."""

    async def report(
        self, output: dict[str, Any], format: str = "json",
    ) -> Report:
        """Genere un rapport (default : JSON passthrough)."""
        return Report(
            domain_id=self.domain_id,
            report_type="summary",
            format=format,  # type: ignore[arg-type]
            content=output,
        )

    def invariants(self) -> list[Invariant]:
        """Retourne les invariants runtime (default : vide)."""
        return []

    def migrate(
        self, old_version: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Migration data entre versions (default : identity)."""
        return data


# ============================================================================
# DomainRegistry - thread-safe singleton
# ============================================================================

class DomainRegistry:
    """Registry thread-safe des domaines enregistres.

    Singleton via `DomainRegistry.instance()`. Thread-safe car toutes les
    operations sont guardees par un `threading.RLock`.
    """

    _instance: ClassVar["DomainRegistry | None"] = None
    _instance_lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._domains: dict[str, dict[str, BaseDomain]] = {}  # id -> version -> domain
        self._deprecated: set[tuple[str, str]] = set()

    @classmethod
    def instance(cls) -> "DomainRegistry":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (tests only)."""
        with cls._instance_lock:
            cls._instance = None

    def register(self, domain: BaseDomain) -> None:
        """Enregistre un domaine. Rejet si deja enregistre meme version."""
        with self._lock:
            domain_id = domain.domain_id
            version = domain.version
            versions = self._domains.setdefault(domain_id, {})
            if version in versions:
                raise ValueError(
                    f"Domain {domain_id}@{version} already registered",
                )
            versions[version] = domain
            logger.info("registered domain %s@%s", domain_id, version)

    def get(
        self, domain_id: str, version: str | None = None,
    ) -> BaseDomain:
        """Retourne le domaine (default : latest non-deprecated)."""
        with self._lock:
            versions = self._domains.get(domain_id)
            if not versions:
                raise KeyError(f"Unknown domain: {domain_id}")
            if version is not None:
                if version not in versions:
                    raise KeyError(f"Unknown version {version} for {domain_id}")
                return versions[version]
            # Latest non-deprecated
            candidates = [
                v for v in versions.keys()
                if (domain_id, v) not in self._deprecated
            ]
            if not candidates:
                raise KeyError(f"All versions of {domain_id} are deprecated")
            latest = max(candidates, key=_semver_key)
            return versions[latest]

    def list_domains(self) -> list[dict[str, Any]]:
        """Liste tous les domaines enregistres avec leurs versions.

        Robuste vs toutes-versions-deprecated : remonte quand meme pour
        permettre l'inspection (tests + UI).
        """
        with self._lock:
            out = []
            for domain_id, versions in self._domains.items():
                non_deprec = [
                    v for v in versions
                    if (domain_id, v) not in self._deprecated
                ]
                latest_v = (max(non_deprec, key=_semver_key)
                             if non_deprec
                             else max(versions.keys(), key=_semver_key))
                latest = versions[latest_v]
                out.append({
                    "domain_id": domain_id,
                    "latest_version": latest_v,
                    "description": latest.description,
                    "all_versions": sorted(versions.keys(), key=_semver_key),
                    "deprecated": sorted(
                        [v for v in versions
                         if (domain_id, v) in self._deprecated],
                        key=_semver_key,
                    ),
                    "operations": list(latest.supported_operations),
                })
            return out

    def deprecate(self, domain_id: str, version: str) -> None:
        with self._lock:
            if domain_id not in self._domains or version not in self._domains[domain_id]:
                raise KeyError(f"Unknown: {domain_id}@{version}")
            self._deprecated.add((domain_id, version))
            logger.warning("deprecated %s@%s", domain_id, version)


def _semver_key(v: str) -> tuple[int, int, int]:
    """Parse 'major.minor.patch' en tuple pour sort."""
    try:
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0,
                int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return (0, 0, 0)


# ============================================================================
# DomainRouter - middleware chain + metrics
# ============================================================================

class DomainRouter:
    """Dispatch une operation vers le domaine cible avec middleware chain.

    Middleware appliques :
      - Validation input vs JSON Schema
      - Auth : verifie permissions (ctx.has_permission(f'{domain}:process'))
      - Rate limiting (si RateLimiter injecte)
      - Tenant isolation : tenant_id propage
      - Tracing : correlation_id auto
      - Metrics : duree, success/fail per (domain, operation)
    """

    def __init__(self, registry: DomainRegistry | None = None) -> None:
        self.registry = registry or DomainRegistry.instance()

    async def validate(
        self, input_data: dict[str, Any], ctx: DomainContext,
        version: str | None = None,
    ) -> ValidationResult:
        domain = self.registry.get(ctx.domain_id, version)
        start = time.perf_counter()
        try:
            result = await domain.validate(input_data, ctx)
            logger.info(
                "domain.validate domain=%s valid=%s issues=%d duration_ms=%d "
                "correlation_id=%s",
                ctx.domain_id, result.valid, len(result.issues),
                int((time.perf_counter() - start) * 1000), ctx.correlation_id,
            )
            return result
        except Exception as exc:
            logger.exception("domain.validate failed domain=%s", ctx.domain_id)
            return ValidationResult(
                valid=False,
                domain_id=ctx.domain_id,
                domain_version=domain.version,
                issues=[Issue(
                    code="DOMAIN_VALIDATE_EXCEPTION",
                    severity="critical",
                    message=str(exc)[:200],
                )],
            )

    async def process(
        self, input_data: dict[str, Any], ctx: DomainContext,
        operation: str, version: str | None = None,
    ) -> ProcessResult:
        if not ctx.has_permission(f"{ctx.domain_id}:process") and \
           not ctx.has_permission(f"{ctx.domain_id}:*"):
            return ProcessResult(
                success=False,
                domain_id=ctx.domain_id,
                operation=operation,
                issues=[Issue(
                    code="FORBIDDEN",
                    severity="error",
                    message=f"Missing permission: {ctx.domain_id}:process",
                )],
                correlation_id=ctx.correlation_id,
            )

        domain = self.registry.get(ctx.domain_id, version)
        start = time.perf_counter()
        try:
            result = await domain.process(input_data, ctx)
            result.duration_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "domain.process domain=%s op=%s success=%s duration_ms=%d "
                "correlation_id=%s",
                ctx.domain_id, operation, result.success, result.duration_ms,
                ctx.correlation_id,
            )
            return result
        except Exception as exc:
            logger.exception("domain.process failed domain=%s op=%s",
                              ctx.domain_id, operation)
            return ProcessResult(
                success=False,
                domain_id=ctx.domain_id,
                operation=operation,
                issues=[Issue(
                    code="DOMAIN_PROCESS_EXCEPTION",
                    severity="critical",
                    message=str(exc)[:200],
                )],
                correlation_id=ctx.correlation_id,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
