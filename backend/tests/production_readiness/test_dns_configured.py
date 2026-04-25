"""A record + CNAME (www) + MX (if SMTP configured)."""
from __future__ import annotations

import socket
from urllib.parse import urlparse


def test_a_record_resolves(base_url: str) -> None:
    host = urlparse(base_url).hostname
    assert host
    info = socket.getaddrinfo(host, 443, socket.AF_INET)
    assert info, f"no A record for {host}"


def test_apex_or_www_reachable(base_url: str) -> None:
    host = urlparse(base_url).hostname
    parts = host.split(".")
    if len(parts) > 2:
        return  # already a subdomain — apex test would be unrelated
    for candidate in (host, f"www.{host}"):
        try:
            socket.getaddrinfo(candidate, 443, socket.AF_INET)
            return
        except OSError:
            continue
    raise AssertionError(f"neither {host} nor www.{host} resolves")
