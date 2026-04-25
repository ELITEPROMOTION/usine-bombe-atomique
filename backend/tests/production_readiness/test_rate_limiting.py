"""Rate limiter must return HTTP 429 after the configured threshold."""
from __future__ import annotations

import urllib.error
import urllib.request


def test_rate_limit_eventually_429(base_url: str) -> None:
    url = f"{base_url}/api/v1/health"
    statuses: list[int] = []
    for _ in range(120):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
                statuses.append(resp.status)
        except urllib.error.HTTPError as exc:
            statuses.append(exc.code)
        if 429 in statuses:
            break
    assert 429 in statuses, \
        f"never hit rate limit in 120 calls (statuses: {set(statuses)})"
