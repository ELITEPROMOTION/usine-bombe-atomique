"""Tests Sentry integration V5.9 — file mode + PII scrubbing."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.observability.sentry_integration import (
    IGNORE_EXCEPTIONS, ErrorEvent, SentryConfig, SentryIntegration, scrub_pii,
)


@pytest.fixture
def sentry(tmp_path, monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    cfg = SentryConfig(
        dsn=None,
        environment="test",
        release="v5.9-test",
        log_file_path=str(tmp_path / "errors.jsonl"),
    )
    SentryIntegration._instance = None  # reset singleton
    return SentryIntegration(cfg)


def test_scrub_email() -> None:
    out = scrub_pii("Contact ahmed@example.dz for help")
    assert "ahmed@example.dz" not in out
    assert "[EMAIL]" in out


def test_scrub_phone_dz_formats() -> None:
    samples = [
        "0555123456",
        "+213555123456",
        "0666987654",
        "0777111222",
    ]
    for s in samples:
        out = scrub_pii(f"Call {s} now")
        assert s not in out, f"{s} not scrubbed"
        assert "[PHONE]" in out


def test_scrub_nif_dz_15_digits() -> None:
    out = scrub_pii("NIF 123456789012345 active")
    assert "123456789012345" not in out
    assert "[NIF]" in out


def test_scrub_combined() -> None:
    text = "User ahmed@dz.com phone 0555123456 NIF 123456789012345"
    out = scrub_pii(text)
    assert "[EMAIL]" in out
    assert "[PHONE]" in out
    assert "[NIF]" in out
    assert "ahmed" not in out


def test_config_mode_file_when_no_dsn(monkeypatch) -> None:
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    cfg = SentryConfig.from_env()
    assert cfg.mode == "file"


def test_config_mode_cloud_when_dsn(monkeypatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", "https://abc@sentry.io/123")
    cfg = SentryConfig.from_env()
    assert cfg.mode == "cloud"


def test_capture_exception_writes_file(sentry) -> None:
    try:
        raise ValueError("boom")
    except ValueError as exc:
        fp = sentry.capture(exc=exc, tenant_id="t1", domain_id="rh")

    assert fp is not None
    assert len(fp) == 16  # truncated SHA256
    contents = Path(sentry.config.log_file_path).read_text().strip()
    parsed = json.loads(contents)
    assert parsed["exc_type"] == "ValueError"
    assert parsed["tenant_id"] == "t1"
    assert parsed["domain_id"] == "rh"


def test_capture_message_only(sentry) -> None:
    fp = sentry.capture(message="custom log line", level="warning")
    assert fp is not None
    parsed = json.loads(Path(sentry.config.log_file_path).read_text().strip())
    assert parsed["exc_type"] == "LogMessage"
    assert parsed["level"] == "warning"


def test_capture_scrubs_pii_in_message(sentry) -> None:
    try:
        raise RuntimeError("Contact ahmed@dz.com on 0555111222")
    except RuntimeError as exc:
        sentry.capture(exc=exc)
    parsed = json.loads(Path(sentry.config.log_file_path).read_text().strip())
    assert "ahmed@dz.com" not in parsed["message"]
    assert "0555111222" not in parsed["message"]
    assert "[EMAIL]" in parsed["message"]
    assert "[PHONE]" in parsed["message"]


def test_capture_ignored_exception_returns_none(sentry) -> None:
    class BrokenPipeError(Exception):
        pass
    fp = sentry.capture(exc=BrokenPipeError("broken"))
    assert fp is None


def test_capture_returns_none_when_empty(sentry) -> None:
    assert sentry.capture() is None


def test_fingerprint_stable_across_calls(sentry) -> None:
    fps = []
    for _ in range(3):
        try:
            raise KeyError("same key")
        except KeyError as exc:
            fps.append(sentry.capture(exc=exc))
    assert len(set(fps)) == 1, "same exception → same fingerprint"


def test_fingerprint_differs_for_different_exceptions(sentry) -> None:
    fps = []
    for cls, msg in [(ValueError, "a"), (ValueError, "b"), (KeyError, "a")]:
        try:
            raise cls(msg)
        except Exception as exc:
            fps.append(sentry.capture(exc=exc))
    assert len(set(fps)) == 3


def test_list_recent(sentry) -> None:
    for i in range(5):
        try:
            raise RuntimeError(f"err {i}")
        except RuntimeError as exc:
            sentry.capture(exc=exc)
    recent = sentry.list_recent(limit=3)
    assert len(recent) == 3
    assert all("fingerprint" in e for e in recent)


def test_grouped_issues(sentry) -> None:
    for _ in range(3):
        try:
            raise ValueError("repeat")
        except ValueError as exc:
            sentry.capture(exc=exc)
    try:
        raise KeyError("once")
    except KeyError as exc:
        sentry.capture(exc=exc)

    groups = sentry.grouped_issues(limit=10)
    counts = {g["exc_type"]: g["count"] for g in groups}
    assert counts.get("ValueError") == 3
    assert counts.get("KeyError") == 1


def test_extra_fields_scrubbed(sentry) -> None:
    try:
        raise RuntimeError("err")
    except RuntimeError as exc:
        sentry.capture(exc=exc, extra={"user_email": "ahmed@dz.com"})
    parsed = json.loads(Path(sentry.config.log_file_path).read_text().strip())
    assert "ahmed@dz.com" not in parsed["extra"]["user_email"]


def test_ignore_set_contents() -> None:
    assert "BrokenPipeError" in IGNORE_EXCEPTIONS
    assert "ConnectionResetError" in IGNORE_EXCEPTIONS
    assert "KeyboardInterrupt" in IGNORE_EXCEPTIONS


def test_singleton_instance() -> None:
    SentryIntegration._instance = None
    a = SentryIntegration.instance()
    b = SentryIntegration.instance()
    assert a is b


def test_error_event_to_json_serializable() -> None:
    e = ErrorEvent(
        exc_type="X", message="m", stack="", fingerprint="abc",
        tenant_id="t1",
    )
    parsed = json.loads(e.to_json())
    assert parsed["exc_type"] == "X"
    assert parsed["tenant_id"] == "t1"
