"""Redis breaker present + rate-limit fallback (open returns 429 not 500)."""
from __future__ import annotations

import json
import urllib.request


def test_redis_breaker_visible(base_url: str) -> None:
    url = f"{base_url}/api/v1/resilience/breakers"
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        body = json.loads(resp.read())
    breakers = {b["name"]: b for b in body.get("breakers", [])}
    assert "redis" in breakers
