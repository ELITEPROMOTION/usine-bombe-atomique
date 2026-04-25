"""Datadog exporter V5.9 - lightweight, dual-mode.

Mode :
  - Si DATADOG_API_KEY present : POST HTTPS vers api.datadoghq.com/.eu
  - Sinon : append vers /var/log/uba/datadog-metrics.jsonl (local,
    lisible par /observability dashboard)

Pas de dependance `datadog` lib. Format metrics natif StatsD / v1 series API.

9 metriques custom UBA :
  - uba.autonomy.decisions.total                 (counter)
  - uba.autonomy.confidence                      (histogram)
  - uba.domain.operations.latency_ms.p99         (gauge)
  - uba.circuit_breakers.state                   (gauge per breaker)
  - uba.slo.availability.ratio                   (gauge)
  - uba.active_learning.agreement_rate           (gauge)
  - uba.knowledge_graph.nodes_total              (gauge)
  - uba.cache.hit_rate                           (gauge per domain)
  - uba.chaos.scenarios.success_rate             (gauge)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("uba.observability.datadog")


_DEFAULT_LOG_DIR = os.environ.get("UBA_DATADOG_LOG_DIR",
                                    str(Path(tempfile.gettempdir()) / "uba_datadog"))
_DEFAULT_LOG_FILE = "datadog-metrics.jsonl"


# Metric types supported (matches Datadog v1 series API)
MetricType = str  # "count" | "gauge" | "rate" | "histogram"


@dataclass
class Metric:
    name: str
    value: float
    metric_type: MetricType = "gauge"
    tags: list[str] = field(default_factory=list)
    timestamp: int = field(default_factory=lambda: int(time.time()))
    host: str = "uba-backend"

    def to_datadog_series(self) -> dict[str, Any]:
        """Format payload Datadog v1 series API."""
        return {
            "metric": self.name,
            "type": self.metric_type,
            "points": [[self.timestamp, self.value]],
            "host": self.host,
            "tags": self.tags,
        }

    def to_jsonl(self) -> str:
        return json.dumps({
            "metric": self.name, "value": self.value,
            "type": self.metric_type, "tags": self.tags,
            "timestamp": self.timestamp, "host": self.host,
        }, default=str)


@dataclass
class DatadogConfig:
    api_key: str | None = None
    site: str = "datadoghq.eu"  # eu/us1/us3/us5
    default_tags: list[str] = field(default_factory=list)
    log_file_path: str = _DEFAULT_LOG_DIR + "/" + _DEFAULT_LOG_FILE
    timeout_s: float = 5.0

    @classmethod
    def from_env(cls) -> "DatadogConfig":
        return cls(
            api_key=os.environ.get("DATADOG_API_KEY") or None,
            site=os.environ.get("DATADOG_SITE", "datadoghq.eu"),
            default_tags=_parse_tags(os.environ.get("DATADOG_TAGS",
                                                       "env:dev,service:uba")),
            log_file_path=os.environ.get("UBA_DATADOG_LOG_FILE",
                                           _DEFAULT_LOG_DIR + "/" + _DEFAULT_LOG_FILE),
        )

    @property
    def mode(self) -> str:
        return "cloud" if self.api_key else "file"


class DatadogExporter:
    """Exporter metrics Datadog avec fallback fichier local."""

    def __init__(self, config: DatadogConfig | None = None) -> None:
        self.config = config or DatadogConfig.from_env()
        if self.config.mode == "file":
            Path(self.config.log_file_path).parent.mkdir(
                parents=True, exist_ok=True,
            )

    async def emit(self, metric: Metric) -> dict[str, Any]:
        """Emet une metrique (cloud ou fichier selon mode)."""
        metric.tags = list(set(metric.tags + self.config.default_tags))
        if self.config.mode == "cloud":
            return await self._emit_cloud([metric])
        return self._emit_file([metric])

    async def emit_batch(self, metrics: list[Metric]) -> dict[str, Any]:
        for m in metrics:
            m.tags = list(set(m.tags + self.config.default_tags))
        if self.config.mode == "cloud":
            return await self._emit_cloud(metrics)
        return self._emit_file(metrics)

    def _emit_file(self, metrics: list[Metric]) -> dict[str, Any]:
        path = Path(self.config.log_file_path)
        with open(path, "a", encoding="utf-8") as fh:
            for m in metrics:
                fh.write(m.to_jsonl() + "\n")
        return {"mode": "file", "count": len(metrics), "path": str(path)}

    async def _emit_cloud(self, metrics: list[Metric]) -> dict[str, Any]:
        url = f"https://api.{self.config.site}/api/v1/series"
        payload = {"series": [m.to_datadog_series() for m in metrics]}
        try:
            async with httpx.AsyncClient(timeout=self.config.timeout_s) as c:
                resp = await c.post(
                    url, json=payload,
                    headers={"DD-API-KEY": self.config.api_key or ""},
                )
            return {"mode": "cloud", "count": len(metrics),
                    "http_status": resp.status_code}
        except Exception as exc:
            # Fallback file sur erreur cloud
            logger.warning("datadog cloud push failed: %s (fallback file)", exc)
            return self._emit_file(metrics)

    # ---------- Convenience methods for each UBA custom metric ----------

    async def autonomy_decisions_total(self, n: int, tags: list[str] | None = None) -> None:
        await self.emit(Metric("uba.autonomy.decisions.total",
                                  float(n), "count", tags or []))

    async def autonomy_confidence(self, value: float, tags: list[str] | None = None) -> None:
        await self.emit(Metric("uba.autonomy.confidence",
                                  float(value), "histogram", tags or []))

    async def domain_latency_p99(self, domain: str, ms: float) -> None:
        await self.emit(Metric("uba.domain.operations.latency_ms.p99",
                                  float(ms), "gauge", [f"domain:{domain}"]))

    async def circuit_breaker_state(self, name: str, state: str) -> None:
        # encode state : closed=0, half_open=1, open=2
        val = {"closed": 0, "half_open": 1, "open": 2}.get(state, -1)
        await self.emit(Metric("uba.circuit_breakers.state",
                                  float(val), "gauge", [f"breaker:{name}"]))

    async def slo_availability(self, slo_name: str, ratio: float) -> None:
        await self.emit(Metric("uba.slo.availability.ratio",
                                  float(ratio), "gauge", [f"slo:{slo_name}"]))

    async def active_learning_agreement(self, rate: float, domain: str | None = None) -> None:
        tags = [f"domain:{domain}"] if domain else []
        await self.emit(Metric("uba.active_learning.agreement_rate",
                                  float(rate), "gauge", tags))

    async def knowledge_graph_nodes(self, n: int) -> None:
        await self.emit(Metric("uba.knowledge_graph.nodes_total",
                                  float(n), "gauge"))

    async def cache_hit_rate(self, domain: str, rate: float) -> None:
        await self.emit(Metric("uba.cache.hit_rate",
                                  float(rate), "gauge", [f"domain:{domain}"]))

    async def chaos_success_rate(self, rate: float) -> None:
        await self.emit(Metric("uba.chaos.scenarios.success_rate",
                                  float(rate), "gauge"))

    # ---------- Collect all metrics at once ----------

    async def collect_snapshot(self, pool: Any) -> dict[str, Any]:
        """Collecte toutes les metriques UBA et les emet en batch."""
        metrics: list[Metric] = []

        # Circuit breakers
        try:
            from app.resilience import CircuitBreakerRegistry
            for cb in CircuitBreakerRegistry.instance().list_all():
                state_val = {"closed": 0, "half_open": 1, "open": 2}.get(
                    cb["state"], -1)
                metrics.append(Metric(
                    "uba.circuit_breakers.state",
                    float(state_val), "gauge",
                    [f"breaker:{cb['name']}"],
                ))
        except Exception as exc:
            logger.debug("breakers snapshot failed: %s", exc)

        # Knowledge graph
        try:
            from app.intelligence.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph(pool)
            stats = await kg.stats()
            metrics.append(Metric(
                "uba.knowledge_graph.nodes_total",
                float(stats["nodes_total"]), "gauge",
            ))
            metrics.append(Metric(
                "uba.knowledge_graph.edges_total",
                float(stats["edges_total"]), "gauge",
            ))
        except Exception as exc:
            logger.debug("kg snapshot failed: %s", exc)

        # Active learning
        try:
            from app.intelligence.active_learner import ActiveLearner
            al = ActiveLearner(pool)
            m = await al.metrics(window_days=7)
            metrics.append(Metric(
                "uba.active_learning.agreement_rate",
                float(m["agreement_rate"]), "gauge",
            ))
            metrics.append(Metric(
                "uba.active_learning.total_loops",
                float(m["total_loops"]), "gauge",
            ))
        except Exception as exc:
            logger.debug("active_learning snapshot failed: %s", exc)

        # SLO
        try:
            from app.observability.slo_tracker import SLOTracker
            tracker = SLOTracker(pool)
            for status in await tracker.status_all():
                metrics.append(Metric(
                    "uba.slo.availability.ratio",
                    float(status.current_sli) / 100.0, "gauge",
                    [f"slo:{status.slo_name}"],
                ))
        except Exception as exc:
            logger.debug("slo snapshot failed: %s", exc)

        result = await self.emit_batch(metrics)
        return {
            "metrics_count": len(metrics),
            "emit_result": result,
            "mode": self.config.mode,
        }


def _parse_tags(raw: str) -> list[str]:
    """Parse 'env:prod,service:uba' -> ['env:prod','service:uba']."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]
