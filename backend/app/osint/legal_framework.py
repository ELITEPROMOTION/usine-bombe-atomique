"""V8 Legal Framework — non-bypassable guards for OSINT modules.

Components :
  * ConsentManager : enregistre, verifie, revoque les consents signes
  * ScopeEnforcer  : whitelist hardcoded Dendani + extensions consenties
  * AuditTrail     : chain hash append-only de toute action OSINT
  * Decorators     : @requires_consent, @log_osint_action, @rate_limit_strict, @dendani_only

Loi DZ 18-07 (donnees personnelles) + 09-04 (cybercrime) : tout module OSINT
doit etre couvert par un de ces decorators. Refus technique automatique sinon.
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable, ClassVar
from uuid import UUID, uuid4

import asyncpg

logger = logging.getLogger("uba.osint.legal")

# Domaines Dendani hardcoded — modifiable uniquement par migration SQL contre-signee.
DENDANI_DOMAIN_WHITELIST: tuple[str, ...] = (
    "dendani.dz",
    "residences.dendani.dz",
    "api.dendani.dz",
    "internal.dendani.dz",
)

DENDANI_IP_WHITELIST: tuple[str, ...] = (
    "127.0.0.1",
    "::1",
)

GENESIS_HASH = "0" * 64


# -----------------------------------------------------------------------------
# Risk levels
# -----------------------------------------------------------------------------


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# -----------------------------------------------------------------------------
# Consent
# -----------------------------------------------------------------------------


@dataclass
class ConsentResult:
    granted: bool
    consent_id: str | None
    target: str
    reason: str
    expires_at: datetime | None = None


@dataclass
class Consent:
    consent_id: str
    target: str
    actions: list[str]
    contractor: str
    contract_pdf_sha256: str
    signed_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


def _normalize_target(target: str) -> str:
    return target.strip().lower()


def _is_dendani_target(target: str) -> bool:
    t = _normalize_target(target)
    if t in DENDANI_IP_WHITELIST:
        return True
    for d in DENDANI_DOMAIN_WHITELIST:
        if t == d or t.endswith("." + d):
            return True
    return False


class ConsentManager:
    """Gere les consents pentest/audit clients hors-Dendani."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add_consent(
        self,
        *,
        target: str,
        actions: list[str],
        contractor: str,
        contract_pdf_sha256: str,
        expires_at: datetime,
        signed_at: datetime | None = None,
    ) -> str:
        if not contract_pdf_sha256 or len(contract_pdf_sha256) != 64:
            raise ValueError("contract_pdf_sha256 must be a 64-char hex hash")
        if not re.fullmatch(r"[0-9a-f]{64}", contract_pdf_sha256):
            raise ValueError("contract_pdf_sha256 must be lowercase hex")
        if expires_at <= datetime.now(timezone.utc):
            raise ValueError("expires_at must be in the future")
        consent_id = str(uuid4())
        signed_at = signed_at or datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO osint_consents
                  (consent_id, target, actions, contractor, contract_pdf_sha256,
                   signed_at, expires_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                UUID(consent_id), _normalize_target(target),
                json.dumps(actions), contractor,
                contract_pdf_sha256, signed_at, expires_at,
            )
        logger.info("consent.added id=%s target=%s contractor=%s", consent_id, target, contractor)
        return consent_id

    async def revoke_consent(self, consent_id: str, reason: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE osint_consents SET revoked_at = NOW(), revoked_reason = $2
                WHERE consent_id = $1 AND revoked_at IS NULL
                """,
                UUID(consent_id), reason,
            )
        logger.info("consent.revoked id=%s reason=%s", consent_id, reason)

    async def check_consent(self, target: str, action: str) -> ConsentResult:
        """Verifie si une cible est couverte par un consent valide pour cette action."""
        norm = _normalize_target(target)
        if _is_dendani_target(norm):
            return ConsentResult(True, None, norm, "dendani-whitelisted")
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT consent_id, actions, expires_at
                FROM osint_consents
                WHERE target = $1
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                ORDER BY signed_at DESC
                LIMIT 1
                """,
                norm,
            )
        if not row:
            return ConsentResult(False, None, norm, "no-active-consent")
        actions = json.loads(row["actions"]) if isinstance(row["actions"], str) else row["actions"]
        if action not in actions and "*" not in actions:
            return ConsentResult(False, str(row["consent_id"]), norm, f"action {action} not covered")
        return ConsentResult(True, str(row["consent_id"]), norm, "consent-active",
                             expires_at=row["expires_at"])

    async def list_active_consents(self) -> list[Consent]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT consent_id, target, actions, contractor, contract_pdf_sha256,
                       signed_at, expires_at, revoked_at, revoked_reason
                FROM osint_consents
                WHERE revoked_at IS NULL AND expires_at > NOW()
                ORDER BY signed_at DESC
                """,
            )
        out = []
        for r in rows:
            actions = json.loads(r["actions"]) if isinstance(r["actions"], str) else r["actions"]
            out.append(Consent(
                consent_id=str(r["consent_id"]),
                target=r["target"],
                actions=actions,
                contractor=r["contractor"],
                contract_pdf_sha256=r["contract_pdf_sha256"],
                signed_at=r["signed_at"],
                expires_at=r["expires_at"],
                revoked_at=r["revoked_at"],
                revoked_reason=r["revoked_reason"],
            ))
        return out


# -----------------------------------------------------------------------------
# Scope enforcement
# -----------------------------------------------------------------------------


class ScopeViolationError(RuntimeError):
    """Raised quand on tente une action OSINT hors scope."""


@dataclass
class ScopeDecision:
    allowed: bool
    target: str
    reason: str
    consent_id: str | None = None


class ScopeEnforcer:
    """Garde-fou unique pour TOUTE action OSINT.

    Refus automatique :
      * target = None / vide
      * target hors whitelist Dendani ET pas de consent valide
      * action non listee dans le consent
    """

    def __init__(self, consent_manager: ConsentManager) -> None:
        self._consents = consent_manager

    async def authorize(self, target: str, action: str) -> ScopeDecision:
        if not target or not target.strip():
            return ScopeDecision(False, target or "", "empty-target")
        norm = _normalize_target(target)
        # Block obvious forbidden patterns (gov/edu without consent)
        if re.search(r"\.(gov|gov\.dz|mil|mil\.dz|edu|edu\.dz)$", norm):
            consent = await self._consents.check_consent(norm, action)
            if not consent.granted:
                return ScopeDecision(False, norm, "gov-edu-target-without-consent")
            return ScopeDecision(True, norm, "consented-gov-edu", consent.consent_id)
        consent = await self._consents.check_consent(norm, action)
        if not consent.granted:
            return ScopeDecision(False, norm, consent.reason)
        return ScopeDecision(True, norm, consent.reason, consent.consent_id)


# -----------------------------------------------------------------------------
# Audit trail (chain-hashed append-only)
# -----------------------------------------------------------------------------


@dataclass
class OsintAuditEvent:
    event_id: str
    actor: str
    module: str
    action: str
    target: str
    risk_level: str
    decision: str
    consent_id: str | None
    payload: dict[str, Any]
    payload_hash: str
    prev_hash: str
    chain_hash: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class AuditTrail:
    """Append-only audit trail avec chain-hash. Tout export RGPD passe par ici."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(
        self,
        *,
        actor: str,
        module: str,
        action: str,
        target: str,
        risk_level: str,
        decision: str,
        consent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        payload = payload or {}
        payload_hash = _sha256(_canon(payload))
        async with self._pool.acquire() as conn, conn.transaction():
            last = await conn.fetchrow(
                "SELECT chain_hash FROM osint_audit_trail "
                "ORDER BY id DESC LIMIT 1 FOR UPDATE",
            )
            prev = last["chain_hash"] if last else GENESIS_HASH
            chain = _sha256(prev + payload_hash)
            row = await conn.fetchrow(
                """
                INSERT INTO osint_audit_trail
                  (event_id, actor, module, action, target, risk_level,
                   decision, consent_id, payload_hash, prev_hash, chain_hash, payload_json)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)
                RETURNING event_id
                """,
                uuid4(), actor, module, action, _normalize_target(target),
                risk_level, decision,
                UUID(consent_id) if consent_id else None,
                payload_hash, prev, chain, _canon(payload),
            )
        return str(row["event_id"])

    async def verify_chain(self, limit: int = 10_000) -> dict[str, Any]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, payload_hash, prev_hash, chain_hash "
                "FROM osint_audit_trail ORDER BY id ASC LIMIT $1",
                limit,
            )
        broken: list[dict[str, Any]] = []
        for r in rows:
            recomputed = _sha256(r["prev_hash"] + r["payload_hash"])
            if recomputed != r["chain_hash"]:
                broken.append({"id": r["id"], "reason": "chain_hash mismatch"})
        return {"events_checked": len(rows), "broken": broken,
                "integrity_ok": len(broken) == 0}

    async def export(self, since: datetime | None = None,
                     until: datetime | None = None) -> list[dict[str, Any]]:
        sql = ("SELECT event_id, actor, module, action, target, risk_level, "
               "decision, consent_id, chain_hash, payload_json, created_at "
               "FROM osint_audit_trail")
        clauses, params = [], []
        if since:
            params.append(since)
            clauses.append(f"created_at >= ${len(params)}")
        if until:
            params.append(until)
            clauses.append(f"created_at <= ${len(params)}")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id ASC"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        out = []
        for r in rows:
            payload = r["payload_json"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            out.append({
                "event_id": str(r["event_id"]),
                "actor": r["actor"],
                "module": r["module"],
                "action": r["action"],
                "target": r["target"],
                "risk_level": r["risk_level"],
                "decision": r["decision"],
                "consent_id": str(r["consent_id"]) if r["consent_id"] else None,
                "chain_hash": r["chain_hash"],
                "payload": payload,
                "created_at": r["created_at"].isoformat(),
            })
        return out


# -----------------------------------------------------------------------------
# Decorators (legal guards)
# -----------------------------------------------------------------------------


_GLOBAL_RATE_BUCKETS: dict[str, list[float]] = {}


def _now() -> float:
    return time.time()


def rate_limit_strict(max_per_hour: int) -> Callable:
    """Limite stricte par module. Hors limite -> ScopeViolationError."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = f"{fn.__module__}.{fn.__qualname__}"
            now = _now()
            bucket = _GLOBAL_RATE_BUCKETS.setdefault(key, [])
            cutoff = now - 3600.0
            _GLOBAL_RATE_BUCKETS[key] = [t for t in bucket if t > cutoff]
            if len(_GLOBAL_RATE_BUCKETS[key]) >= max_per_hour:
                raise ScopeViolationError(
                    f"rate-limit exceeded ({max_per_hour}/h) for {key}"
                )
            _GLOBAL_RATE_BUCKETS[key].append(now)
            return await fn(*args, **kwargs)
        return wrapper

    return deco


def dendani_only(target_param: str = "target") -> Callable:
    """Refuse toute target hors whitelist Dendani. PAS d'override possible."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            target = kwargs.get(target_param)
            if target is None and args:
                # tente positional
                try:
                    target = args[0]
                except IndexError:
                    target = None
            if not target or not _is_dendani_target(str(target)):
                raise ScopeViolationError(
                    f"@dendani_only refuse target='{target}' (whitelist hardcoded)"
                )
            return await fn(*args, **kwargs)
        return wrapper

    return deco


def requires_consent(target_param: str = "target", action: str = "scan") -> Callable:
    """Refuse si target hors-Dendani sans consent valide pour `action`."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            from app.osint.legal_framework import _resolve_pool  # late
            target = kwargs.get(target_param) or (args[0] if args else None)
            if not target:
                raise ScopeViolationError("@requires_consent : target manquant")
            pool = await _resolve_pool()
            mgr = ConsentManager(pool)
            enforcer = ScopeEnforcer(mgr)
            decision = await enforcer.authorize(str(target), action)
            if not decision.allowed:
                raise ScopeViolationError(
                    f"@requires_consent({target}, {action}) refused: {decision.reason}"
                )
            kwargs.setdefault("_consent_id", decision.consent_id)
            return await fn(*args, **kwargs)
        return wrapper

    return deco


def log_osint_action(risk_level: str | RiskLevel = RiskLevel.LOW,
                     module: str | None = None) -> Callable:
    """Append a entry au audit trail (decision=allowed/denied, payload diff)."""

    def deco(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            from app.osint.legal_framework import _resolve_pool
            target = kwargs.get("target") or (args[0] if args else "n/a")
            mod = module or fn.__module__.split(".")[-1]
            pool = await _resolve_pool()
            trail = AuditTrail(pool)
            consent_id = kwargs.pop("_consent_id", None)
            actor = kwargs.get("_actor") or "system"
            try:
                result = await fn(*args, **kwargs)
                await trail.append(
                    actor=actor, module=mod, action=fn.__name__,
                    target=str(target),
                    risk_level=str(risk_level.value if isinstance(risk_level, RiskLevel) else risk_level),
                    decision="allowed",
                    consent_id=consent_id,
                    payload={"ok": True, "summary": _safe_summary(result)},
                )
                return result
            except ScopeViolationError as exc:
                await trail.append(
                    actor=actor, module=mod, action=fn.__name__,
                    target=str(target),
                    risk_level=str(risk_level.value if isinstance(risk_level, RiskLevel) else risk_level),
                    decision="denied",
                    consent_id=consent_id,
                    payload={"reason": str(exc)},
                )
                raise
            except Exception as exc:
                await trail.append(
                    actor=actor, module=mod, action=fn.__name__,
                    target=str(target),
                    risk_level=str(risk_level.value if isinstance(risk_level, RiskLevel) else risk_level),
                    decision="error",
                    consent_id=consent_id,
                    payload={"error": str(exc)[:500]},
                )
                raise
        return wrapper

    return deco


def _safe_summary(result: Any, max_len: int = 240) -> str:
    if result is None:
        return "None"
    try:
        s = json.dumps(result, default=str)[:max_len]
    except Exception:
        s = str(result)[:max_len]
    return s


# -----------------------------------------------------------------------------
# Pool resolver — accepte injection en test
# -----------------------------------------------------------------------------

_INJECTED_POOL: asyncpg.Pool | None = None


def inject_pool_for_test(pool: asyncpg.Pool | None) -> None:
    global _INJECTED_POOL
    _INJECTED_POOL = pool


async def _resolve_pool() -> asyncpg.Pool:
    if _INJECTED_POOL is not None:
        return _INJECTED_POOL
    from app.database import get_pool
    return get_pool()


__all__ = [
    "AuditTrail",
    "Consent",
    "ConsentManager",
    "ConsentResult",
    "DENDANI_DOMAIN_WHITELIST",
    "DENDANI_IP_WHITELIST",
    "OsintAuditEvent",
    "RiskLevel",
    "ScopeDecision",
    "ScopeEnforcer",
    "ScopeViolationError",
    "dendani_only",
    "inject_pool_for_test",
    "log_osint_action",
    "rate_limit_strict",
    "requires_consent",
]
