"""Fixtures communes pour les tests domaines V5.6."""
from __future__ import annotations

import pytest_asyncio

from app.core import DomainContext, DomainRegistry
from app.domains import register_all


@pytest_asyncio.fixture(scope="module")
async def registry() -> DomainRegistry:
    """Registry avec les 5 domaines charges."""
    return register_all()


def make_ctx(domain_id: str, tenant_id: str = "test-tenant",
              user_id: str | None = "test-user") -> DomainContext:
    return DomainContext(
        tenant_id=tenant_id,
        user_id=user_id,
        domain_id=domain_id,
        permissions=frozenset([f"{domain_id}:*"]),
    )
