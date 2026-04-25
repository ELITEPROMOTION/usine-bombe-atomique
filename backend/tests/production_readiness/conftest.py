"""Production readiness tests fixtures.

These tests are SKIPPED unless `UBA_ENV` is `staging` or `production`. This
keeps `pytest tests/` green in dev/CI but lets ops run the full validation
suite after a real deploy with `UBA_ENV=production pytest tests/production_readiness/`.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


def pytest_collection_modifyitems(config, items: list[pytest.Item]) -> None:
    """Mark every test in this dir as `skip` unless on staging/prod."""
    env = os.environ.get("UBA_ENV", "dev").lower()
    if env in {"staging", "production"}:
        return
    skip_marker = pytest.mark.skip(
        reason=f"production_readiness/* skipped when UBA_ENV={env!r} (run with staging/production)",
    )
    for item in items:
        if "production_readiness" in str(item.fspath):
            item.add_marker(skip_marker)


@pytest.fixture
def base_url() -> str:
    return os.environ.get("UBA_BASE_URL", "https://uba.dendani.dz")


@pytest.fixture
def admin_token() -> Iterator[str]:
    yield os.environ.get("UBA_ADMIN_TOKEN", "")
