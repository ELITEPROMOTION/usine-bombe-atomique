"""Datadog/Sentry/OTel must report mode != 'error'."""
from __future__ import annotations

import json
import urllib.request


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        return json.loads(resp.read())


def test_datadog_status(base_url: str) -> None:
    body = _get(f"{base_url}/api/v1/observability/datadog/status")
    assert body["mode"] in {"file", "cloud"}


def test_sentry_status(base_url: str) -> None:
    body = _get(f"{base_url}/api/v1/observability/sentry/status")
    assert body["mode"] in {"file", "cloud"}


def test_otel_status(base_url: str) -> None:
    body = _get(f"{base_url}/api/v1/observability/otel/status")
    assert body.get("initialized") is True
