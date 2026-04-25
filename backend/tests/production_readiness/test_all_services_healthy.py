"""15 health checks on /health/v2 endpoint."""
from __future__ import annotations

import json
import urllib.request


def test_health_v2_all_15_checks_green(base_url: str) -> None:
    url = f"{base_url}/api/v1/health/v2"
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        body = json.loads(resp.read())
    checks = body.get("checks", [])
    assert len(checks) >= 15, f"expected >= 15 health checks, got {len(checks)}"
    failed = [c["name"] for c in checks if c.get("status") != "ok"]
    assert not failed, f"failing checks: {failed}"
    assert body.get("overall") == "ok"
