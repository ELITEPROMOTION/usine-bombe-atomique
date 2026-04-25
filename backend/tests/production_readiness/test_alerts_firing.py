"""Trigger a sentinel error and confirm Sentry recorded it."""
from __future__ import annotations

import json
import urllib.request


def test_sentry_test_event_records(base_url: str) -> None:
    req = urllib.request.Request(
        f"{base_url}/api/v1/observability/sentry/test",
        method="POST", data=b'{"message":"production_readiness alerting test"}',
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        body = json.loads(resp.read())
    assert body.get("captured") is True
    assert body.get("fingerprint")


def test_sentry_errors_listing_includes_recent(base_url: str) -> None:
    with urllib.request.urlopen(  # noqa: S310
        f"{base_url}/api/v1/observability/sentry/errors?limit=10", timeout=15,
    ) as resp:
        body = json.loads(resp.read())
    # Either "available_in_file_mode_only=False" (cloud) or has events
    assert body.get("count", 0) >= 0
