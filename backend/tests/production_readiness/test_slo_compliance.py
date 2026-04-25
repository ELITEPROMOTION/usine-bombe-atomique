"""1h rolling SLO must be >= 99.5%."""
from __future__ import annotations

import json
import urllib.request


def test_slo_window_1h_above_995(base_url: str) -> None:
    url = f"{base_url}/api/v1/slo/status?window=1h"
    with urllib.request.urlopen(url, timeout=15) as resp:  # noqa: S310
        body = json.loads(resp.read())
    statuses = body.get("statuses", body.get("slos", []))
    assert statuses
    for s in statuses:
        sli = s.get("current_sli", s.get("sli", 100.0))
        assert sli >= 99.5, f"{s.get('slo_name', s)}: SLI={sli} < 99.5"
