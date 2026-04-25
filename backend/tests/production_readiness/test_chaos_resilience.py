"""Run the chaos scenarios catalog and assert all recover."""
from __future__ import annotations

import json
import urllib.request


def test_chaos_catalog_all_recover(base_url: str, admin_token: str) -> None:
    if not admin_token:
        import pytest
        pytest.skip("UBA_ADMIN_TOKEN not set")
    req = urllib.request.Request(
        f"{base_url}/api/v1/resilience/chaos/run",
        method="POST", data=b'{"scenario_ids": ["all"]}',
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
        body = json.loads(resp.read())
    runs = body.get("runs", [])
    assert len(runs) >= 5
    failed = [r["scenario_id"] for r in runs if r.get("recovered") is False]
    assert not failed, f"chaos scenarios that failed to recover: {failed}"
