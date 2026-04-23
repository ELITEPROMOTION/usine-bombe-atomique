"""Agent #05 Datadog - genere les fichiers de monitoring.

Produit :
- monitoring/datadog.yaml : synthetic API check sur /health
- monitoring/dashboard.json : dashboard 4 widgets (uptime, latency p95, err rate, throughput)
- monitoring/monitors.yaml : 3 monitors (5xx spike, p95 latency, service down)

Zero appel reseau : generation deterministe a partir du manifest + spec.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace


class DatadogAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-05-datadog", name="Datadog Monitor", version="1.0.0")
        self.category = "monitoring"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        spec: str = inputs.get("spec", "")
        manifest: list[dict[str, Any]] = inputs.get("manifest") or workspace.manifest()
        service_name = _service_name(spec)
        endpoints = _extract_endpoints(workspace, manifest)

        files = {
            "monitoring/datadog.yaml": _yaml_synthetic(service_name, endpoints),
            "monitoring/dashboard.json": _dashboard(service_name),
            "monitoring/monitors.yaml": _monitors(service_name),
        }
        for p, c in files.items():
            workspace.write(p, c)

        # Score : 1.0 si 3 fichiers emis + >=1 endpoint detecte
        ok = len(files) == 3 and len(endpoints) >= 1
        return {
            "score": 1.0 if ok else 0.7,
            "passed": ok,
            "service_name": service_name,
            "endpoints_monitored": endpoints,
            "files_written": sorted(files.keys()),
        }


def _service_name(spec: str) -> str:
    m = re.search(r"([a-zA-Z][a-zA-Z0-9_-]{2,})", spec or "app")
    return (m.group(1).lower() if m else "app")[:32]


ENDPOINT_RE = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch)\(\s*"([^"]+)"')


def _extract_endpoints(workspace: Workspace, manifest: list[dict[str, Any]]) -> list[str]:
    endpoints: set[str] = set()
    for meta in manifest:
        path = str(meta.get("path", ""))
        if not path.endswith(".py"):
            continue
        try:
            content = workspace.read(path)
        except FileNotFoundError:
            continue
        for _, ep in ENDPOINT_RE.findall(content):
            endpoints.add(ep)
    # Toujours /health si present dans code
    return sorted(endpoints)[:10]


def _yaml_synthetic(service: str, endpoints: list[str]) -> str:
    primary = endpoints[0] if endpoints else "/health"
    return f"""# Datadog Synthetic API Check - genere par UBA V2
synthetics:
  - name: "{service} · availability"
    type: api
    subtype: http
    request:
      method: GET
      url: "https://{service}.dendani.dz{primary}"
      timeout: 30
    assertions:
      - type: statusCode
        operator: is
        target: 200
      - type: responseTime
        operator: lessThan
        target: 1500
    locations:
      - pl:aws-eu-west-3
      - pl:aws-eu-central-1
    options:
      tick_every: 60
      min_failure_duration: 120
      min_location_failed: 1
    tags:
      - env:production
      - service:{service}
      - owner:dendani
"""


def _dashboard(service: str) -> str:
    payload = {
        "title": f"{service} · service overview",
        "description": "Dashboard UBA V2 - ECS Fargate + ALB + RDS + Redis",
        "widgets": [
            {
                "definition": {
                    "type": "query_value",
                    "title": "Uptime (24h)",
                    "requests": [{"q": f"avg:synthetics.http.response.status{{service:{service}}}"}],
                },
            },
            {
                "definition": {
                    "type": "timeseries",
                    "title": "Latency p95 (ms)",
                    "requests": [{"q": f"p95:trace.fastapi.request.duration{{service:{service}}}"}],
                },
            },
            {
                "definition": {
                    "type": "timeseries",
                    "title": "Error rate 5xx",
                    "requests": [{"q": f"sum:fastapi.requests.5xx{{service:{service}}}.as_rate()"}],
                },
            },
            {
                "definition": {
                    "type": "timeseries",
                    "title": "Throughput req/s",
                    "requests": [{"q": f"sum:fastapi.requests.total{{service:{service}}}.as_rate()"}],
                },
            },
        ],
        "layout_type": "ordered",
        "tags": ["project:dendani", f"service:{service}"],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _monitors(service: str) -> str:
    return f"""# Datadog Monitors - genere par UBA V2
monitors:
  - name: "[{service}] Service down"
    type: service check
    query: '"http.can_connect".over("service:{service}").by("host").last(2).count_by_status()'
    message: |
      Le service {service} ne repond plus.
      Runbook: https://runbooks.dendani.dz/{service}/outage
      @pagerduty-critical
    tags: [env:production, service:{service}, severity:critical]

  - name: "[{service}] p95 latency > 1500 ms"
    type: query alert
    query: 'avg(last_10m):p95:trace.fastapi.request.duration{{service:{service}}} > 1.5'
    message: "Latence p95 degradee. @slack-ops"
    tags: [env:production, service:{service}, severity:warning]

  - name: "[{service}] 5xx spike > 2 err/s"
    type: query alert
    query: 'sum(last_5m):sum:fastapi.requests.5xx{{service:{service}}}.as_rate() > 2'
    message: "Pic d'erreurs 5xx. @slack-ops"
    tags: [env:production, service:{service}, severity:warning]
"""
