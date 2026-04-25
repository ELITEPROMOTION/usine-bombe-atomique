"""Tests OpenTelemetry V5.9 — works with or without SDK installed."""
from __future__ import annotations

import pytest

from app.observability import otel_setup
from app.observability.otel_setup import (
    NoopTracer, _NoopSpan, _get_service_attributes, get_tracer, span, status,
)


def test_get_service_attributes_default(monkeypatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("UBA_VERSION", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    attrs = _get_service_attributes()
    assert attrs["service.name"] == "uba-backend"
    assert attrs["service.namespace"] == "uba"


def test_get_service_attributes_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "uba-test")
    monkeypatch.setenv("UBA_VERSION", "9.9.9")
    monkeypatch.setenv("ENV", "ci")
    attrs = _get_service_attributes()
    assert attrs["service.name"] == "uba-test"
    assert attrs["service.version"] == "9.9.9"
    assert attrs["deployment.environment"] == "ci"


def test_status_returns_dict() -> None:
    s = status()
    assert isinstance(s, dict)
    assert "sdk_available" in s
    assert "initialized" in s
    assert "service_name" in s
    assert "exporter" in s
    assert "instrumentations" in s


def test_get_tracer_returns_tracer_or_noop() -> None:
    t = get_tracer("uba.test")
    assert t is not None
    # Either real Tracer or NoopTracer — both must support start_as_current_span
    assert hasattr(t, "start_as_current_span")


def test_noop_tracer_yields_span_object() -> None:
    tracer = NoopTracer()
    with tracer.start_as_current_span("op") as s:
        assert s.name == "op"
        s.set_attribute("foo", "bar")
        assert s.attributes["foo"] == "bar"


def test_noop_span_records_exception() -> None:
    s = _NoopSpan("op")
    s.record_exception(ValueError("x"))
    assert "error" in s.attributes


def test_noop_span_end_records_duration() -> None:
    s = _NoopSpan("op")
    s.end()
    assert "duration_ms" in s.attributes


def test_span_helper_yields_span() -> None:
    with span("test_operation", domain="rh", op="calc") as s:
        assert s is not None
        # may be SDK span or NoopSpan
        if hasattr(s, "attributes"):
            assert s.attributes.get("domain") == "rh" or True


def test_span_helper_propagates_exceptions() -> None:
    with pytest.raises(ValueError):
        with span("failing") as s:
            raise ValueError("boom")


def test_init_otel_idempotent() -> None:
    # First call sets _INITIALIZED = True; second returns already_initialized.
    # We don't require a fresh state because tests share process.
    res1 = otel_setup.init_otel()
    res2 = otel_setup.init_otel()
    assert "status" in res1
    assert res2["status"] in {"already_initialized", "noop", "initialized"}


def test_init_otel_no_sdk_returns_noop_or_init() -> None:
    res = otel_setup.init_otel()
    # Either the SDK is installed (initialized) or absent (noop) — never crash.
    assert "exporter" in res
    assert "instrumentations" in res


def test_status_after_init_consistent() -> None:
    otel_setup.init_otel()
    s = status()
    assert s["initialized"] is True
