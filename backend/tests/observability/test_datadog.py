"""Tests Datadog exporter V5.9 — file mode only (no API key)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.observability.datadog_exporter import (
    DatadogConfig, DatadogExporter, Metric, _parse_tags,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
def exporter(tmp_path, monkeypatch):
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    cfg = DatadogConfig(
        api_key=None,
        log_file_path=str(tmp_path / "metrics.jsonl"),
        default_tags=["env:test", "service:uba"],
    )
    return DatadogExporter(cfg)


def test_metric_to_jsonl_round_trip() -> None:
    m = Metric("uba.x", 1.5, "gauge", ["a:b"], timestamp=42, host="h1")
    parsed = json.loads(m.to_jsonl())
    assert parsed["metric"] == "uba.x"
    assert parsed["value"] == 1.5
    assert parsed["type"] == "gauge"
    assert parsed["tags"] == ["a:b"]
    assert parsed["timestamp"] == 42
    assert parsed["host"] == "h1"


def test_metric_to_datadog_series_shape() -> None:
    m = Metric("uba.y", 2.0, "count", ["k:v"], timestamp=100)
    s = m.to_datadog_series()
    assert s["metric"] == "uba.y"
    assert s["type"] == "count"
    assert s["points"] == [[100, 2.0]]
    assert s["tags"] == ["k:v"]


def test_parse_tags_basic() -> None:
    assert _parse_tags("env:dev,service:uba") == ["env:dev", "service:uba"]
    assert _parse_tags("") == []
    assert _parse_tags("  a:b ,, c:d ") == ["a:b", "c:d"]


def test_config_from_env_no_api_key(monkeypatch) -> None:
    monkeypatch.delenv("DATADOG_API_KEY", raising=False)
    monkeypatch.setenv("DATADOG_TAGS", "env:ci")
    cfg = DatadogConfig.from_env()
    assert cfg.api_key is None
    assert cfg.mode == "file"
    assert "env:ci" in cfg.default_tags


def test_config_mode_cloud_when_api_key(monkeypatch) -> None:
    monkeypatch.setenv("DATADOG_API_KEY", "fake-key")
    cfg = DatadogConfig.from_env()
    assert cfg.mode == "cloud"


async def test_emit_writes_to_file(exporter, tmp_path) -> None:
    m = Metric("uba.test.x", 7.0, "gauge", ["t:a"])
    res = await exporter.emit(m)
    assert res["mode"] == "file"
    assert res["count"] == 1
    contents = Path(exporter.config.log_file_path).read_text(encoding="utf-8")
    parsed = json.loads(contents.strip())
    assert parsed["metric"] == "uba.test.x"
    assert "env:test" in parsed["tags"]


async def test_emit_batch_appends_all(exporter) -> None:
    metrics = [Metric(f"uba.b.{i}", float(i), "gauge") for i in range(5)]
    res = await exporter.emit_batch(metrics)
    assert res["count"] == 5
    lines = Path(exporter.config.log_file_path).read_text().strip().splitlines()
    assert len(lines) == 5


async def test_default_tags_applied(exporter) -> None:
    m = Metric("uba.tagtest", 1.0, "gauge", ["custom:1"])
    await exporter.emit(m)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert "custom:1" in parsed["tags"]
    assert "env:test" in parsed["tags"]
    assert "service:uba" in parsed["tags"]


async def test_autonomy_decisions_total(exporter) -> None:
    await exporter.autonomy_decisions_total(42, ["domain:fiscal"])
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.autonomy.decisions.total"
    assert parsed["value"] == 42.0


async def test_autonomy_confidence(exporter) -> None:
    await exporter.autonomy_confidence(0.87)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.autonomy.confidence"
    assert parsed["type"] == "histogram"


async def test_domain_latency_p99(exporter) -> None:
    await exporter.domain_latency_p99("rh", 123.4)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.domain.operations.latency_ms.p99"
    assert "domain:rh" in parsed["tags"]


async def test_circuit_breaker_state_encoding(exporter) -> None:
    for state, expected in [("closed", 0.0), ("half_open", 1.0), ("open", 2.0)]:
        await exporter.circuit_breaker_state(f"bk_{state}", state)
    lines = Path(exporter.config.log_file_path).read_text().strip().splitlines()
    values = [json.loads(l)["value"] for l in lines]
    assert values == [0.0, 1.0, 2.0]


async def test_slo_availability(exporter) -> None:
    await exporter.slo_availability("api_latency", 0.995)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.slo.availability.ratio"
    assert "slo:api_latency" in parsed["tags"]


async def test_active_learning_agreement(exporter) -> None:
    await exporter.active_learning_agreement(0.78, domain="fiscal_dz")
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.active_learning.agreement_rate"
    assert "domain:fiscal_dz" in parsed["tags"]


async def test_knowledge_graph_nodes(exporter) -> None:
    await exporter.knowledge_graph_nodes(150)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["value"] == 150.0


async def test_cache_hit_rate(exporter) -> None:
    await exporter.cache_hit_rate("juridique", 0.92)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert "domain:juridique" in parsed["tags"]


async def test_chaos_success_rate(exporter) -> None:
    await exporter.chaos_success_rate(0.97)
    parsed = json.loads(Path(exporter.config.log_file_path).read_text().strip())
    assert parsed["metric"] == "uba.chaos.scenarios.success_rate"


async def test_collect_snapshot_returns_dict(exporter, pool) -> None:
    res = await exporter.collect_snapshot(pool)
    assert "metrics_count" in res
    assert "mode" in res
    assert res["mode"] == "file"


async def test_log_file_directory_auto_created(tmp_path) -> None:
    nested = tmp_path / "deep" / "nested" / "dir" / "out.jsonl"
    cfg = DatadogConfig(api_key=None, log_file_path=str(nested))
    exp = DatadogExporter(cfg)
    await exp.emit(Metric("uba.dirtest", 1.0))
    assert nested.exists()
