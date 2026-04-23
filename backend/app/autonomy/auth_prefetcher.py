"""V5.1 BLOC 3 - Auth Prefetcher.

Detection precoce : avant que l'agent dise "j'ai besoin d'un compte",
le prefetcher regarde :
  1. Vault (credential_vault_universal)
  2. Fallback chain (open-source / free tier)
  3. Lease deja accorde (permission_lease_manager)

Retour structure : {should_ask: bool, path: str, source: str, details: ...}

Ce module est appele par le user_interaction_router AVANT d'accepter une
demande de type A (bypass si possible).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg

from app.autonomy import (
    credential_vault_universal,
    fallback_chain,
    permission_lease_manager,
)


@dataclass
class PrefetchResult:
    should_ask: bool
    path: str                      # "vault" | "fallback" | "lease" | "ask"
    source: str | None
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "should_ask": self.should_ask, "path": self.path,
            "source": self.source, "details": self.details,
        }


async def prefetch(
    pool: asyncpg.Pool, service_name: str, *,
    scope: str | None = None,
) -> PrefetchResult:
    # 1. Vault
    cred = credential_vault_universal.lookup(service_name)
    if cred:
        return PrefetchResult(
            should_ask=False, path="vault", source="vault:credentials",
            details={"has_email": "email" in cred,
                      "has_token": "token" in cred,
                      "last_used_at": cred.get("last_used_at")},
        )

    # 2. Lease
    effective_scope = scope or f"credentials.{service_name.lower()}"
    lease = await permission_lease_manager.find_active(pool, effective_scope)
    if lease:
        return PrefetchResult(
            should_ask=False, path="lease", source=f"lease#{lease.id}",
            details={"expires_at": lease.expires_at.isoformat(),
                      "remaining": lease.usage_cap - lease.usage_count},
        )

    # 3. Fallback
    fb = fallback_chain.find(service_name)
    if not fb.should_still_ask:
        return PrefetchResult(
            should_ask=False, path="fallback",
            source=(fb.recommended or {}).get("name"),
            details=fb.to_dict(),
        )

    # 4. Ask necessaire
    return PrefetchResult(
        should_ask=True, path="ask", source=None,
        details={"fallback_considered": fb.to_dict()},
    )
