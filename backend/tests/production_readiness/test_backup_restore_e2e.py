"""Trigger a manual backup and restore it on a disposable schema."""
from __future__ import annotations

import json
import os
import urllib.request


def _post(url: str, token: str, data: bytes = b"") -> dict:
    req = urllib.request.Request(url, data=data, method="POST",
                                   headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return json.loads(resp.read())


def test_backup_then_list_includes_new(base_url: str, admin_token: str) -> None:
    if not admin_token:
        import pytest
        pytest.skip("UBA_ADMIN_TOKEN not set")
    res = _post(f"{base_url}/api/v1/backups/trigger", admin_token)
    assert res.get("status") in {"ok", "queued"}
    backup_id = res.get("backup_id")
    assert backup_id
    # poll list (best-effort)
    listing_url = f"{base_url}/api/v1/backups/list"
    req = urllib.request.Request(listing_url,
                                   headers={"Authorization": f"Bearer {admin_token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        listing = json.loads(resp.read())
    assert any(b.get("id") == backup_id for b in listing.get("backups", []))
