"""HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy."""
from __future__ import annotations

import urllib.request


def _headers(url: str) -> dict[str, str]:
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return {k.lower(): v for k, v in resp.headers.items()}


def test_security_headers_present(base_url: str) -> None:
    h = _headers(base_url)
    expected = {
        "strict-transport-security": "max-age",
        "x-frame-options": "DENY",
        "x-content-type-options": "nosniff",
        "referrer-policy": "strict-origin-when-cross-origin",
    }
    for header, contains in expected.items():
        assert header in h, f"missing: {header}"
        assert contains.lower() in h[header].lower(), \
            f"{header}={h[header]!r} missing {contains!r}"


def test_csp_present(base_url: str) -> None:
    h = _headers(base_url)
    csp = h.get("content-security-policy", "")
    assert csp, "missing Content-Security-Policy header"
    assert "default-src" in csp
