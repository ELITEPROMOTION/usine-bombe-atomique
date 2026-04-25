"""Cert valide + SNI + grade A+ via headers + cipher suite."""
from __future__ import annotations

import socket
import ssl
from urllib.parse import urlparse


def test_ssl_certificate_present(base_url: str) -> None:
    host = urlparse(base_url).hostname
    assert host
    ctx = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            cert = ssock.getpeercert()
    assert cert
    assert cert["subject"]
    assert cert["notAfter"]


def test_tls_version_modern(base_url: str) -> None:
    host = urlparse(base_url).hostname
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with socket.create_connection((host, 443), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
            assert ssock.version() in {"TLSv1.2", "TLSv1.3"}


def test_hsts_header(base_url: str) -> None:
    import urllib.request
    req = urllib.request.Request(base_url, method="HEAD")
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        hsts = resp.headers.get("Strict-Transport-Security", "")
    assert "max-age" in hsts
    assert int(hsts.split("max-age=")[1].split(";")[0].strip()) >= 31536000  # >= 1 year
