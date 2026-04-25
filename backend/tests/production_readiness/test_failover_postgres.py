"""Verify graceful degradation when postgres goes away."""
from __future__ import annotations

import json
import urllib.request


def test_postgres_breaker_state_visible(base_url: str) -> None:
    url = f"{base_url}/api/v1/resilience/breakers"
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        body = json.loads(resp.read())
    breakers = {b["name"]: b for b in body.get("breakers", [])}
    assert "postgres" in breakers
    assert breakers["postgres"]["state"] in {"closed", "half_open", "open"}
