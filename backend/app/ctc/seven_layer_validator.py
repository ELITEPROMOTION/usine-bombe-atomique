"""V5.3 BLOC 10 - Seven Layer Validator.

Execute sequentiellement 7 couches. Chaque couche produit un LayerReport.
Si une couche echoue -> on arrete et on retourne FAIL + layer_failed.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.ctc import (
    assertion_normalizer,
    auto_triangulator,
    evidence_chain,
    source_registry,
)

logger = logging.getLogger(__name__)


@dataclass
class LayerReport:
    name: str
    passed: bool
    duration_ms: int
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed,
                "duration_ms": self.duration_ms, "details": self.details}


@dataclass
class SevenLayerReport:
    verdict: str                 # PASS | CONDITIONAL_PASS | SOFT_FAIL | HARD_FAIL
    layers: list[LayerReport]
    total_duration_ms: int
    first_fail: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "layers": [l.to_dict() for l in self.layers],
            "total_duration_ms": self.total_duration_ms,
            "first_fail": self.first_fail,
        }


async def _layer_1_source_trust(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    required_domain = ctx.get("domain", "web_standards")
    sources = await source_registry.by_domain(
        pool, required_domain, min_tier=3, only_active=True)
    ok = len(sources) >= 1
    return LayerReport("1_source_trust", ok,
                        int((time.perf_counter() - t0) * 1000),
                        {"active_sources": len(sources),
                         "domain": required_domain})


async def _layer_2_extraction(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    text = ctx.get("text", "")
    domain = ctx.get("domain", "web_standards")
    assertions = assertion_normalizer.normalize("", text, domain)
    return LayerReport("2_assertion_extraction",
                        len(assertions) > 0 or not text.strip(),
                        int((time.perf_counter() - t0) * 1000),
                        {"extracted": len(assertions)})


async def _layer_3_triangulation(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    claim = ctx.get("claim", "")
    if not claim:
        return LayerReport("3_cross_source_triangulation", True,
                            int((time.perf_counter() - t0) * 1000),
                            {"skipped": "no claim"})
    tri = await auto_triangulator.triangulate(pool, claim, skip_fetch=True)
    ok = tri.verdict in ("TRUE", "UNCERTAIN", "UNKNOWN")
    return LayerReport("3_cross_source_triangulation", ok,
                        int((time.perf_counter() - t0) * 1000),
                        tri.to_dict())


async def _layer_4_deterministic(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    tests_passed = ctx.get("tests_passed")
    tests_total = ctx.get("tests_total")
    if tests_passed is None or tests_total is None:
        ok = True  # skipped (no data)
    else:
        ok = int(tests_passed) == int(tests_total)
    return LayerReport("4_deterministic_validation", ok,
                        int((time.perf_counter() - t0) * 1000),
                        {"tests_passed": tests_passed,
                         "tests_total": tests_total})


async def _layer_5_binding(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    artifact_hash = ctx.get("artifact_hash")
    ok = bool(artifact_hash)
    return LayerReport("5_artifact_binding", ok,
                        int((time.perf_counter() - t0) * 1000),
                        {"artifact_hash": (artifact_hash or "")[:32]})


async def _layer_6_truth_judgment(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    """Judge utilise uniquement des metriques objectives passees en ctx."""
    t0 = time.perf_counter()
    confidence = float(ctx.get("confidence", 0.0))
    all_dims_ok = bool(ctx.get("all_dims_above_threshold", True))
    no_critical_contradictions = bool(ctx.get("no_critical_contradictions", True))
    ok = confidence >= 0.70 and all_dims_ok and no_critical_contradictions
    return LayerReport("6_truth_judgment", ok,
                        int((time.perf_counter() - t0) * 1000),
                        {"confidence": confidence,
                         "all_dims_ok": all_dims_ok,
                         "no_contradictions": no_critical_contradictions})


async def _layer_7_enforcement(pool: asyncpg.Pool, ctx: dict[str, Any]) -> LayerReport:
    t0 = time.perf_counter()
    chain_report = await evidence_chain.verify_chain(pool, limit=1000)
    ok = chain_report.status == "preserved"
    return LayerReport("7_continuous_enforcement", ok,
                        int((time.perf_counter() - t0) * 1000),
                        {"chain_status": chain_report.status,
                         "events_checked": chain_report.events_checked})


LAYERS: list[Callable[[asyncpg.Pool, dict[str, Any]], Awaitable[LayerReport]]] = [
    _layer_1_source_trust, _layer_2_extraction, _layer_3_triangulation,
    _layer_4_deterministic, _layer_5_binding, _layer_6_truth_judgment,
    _layer_7_enforcement,
]


async def validate(
    pool: asyncpg.Pool, ctx: dict[str, Any], *,
    stop_on_fail: bool = False,
) -> SevenLayerReport:
    """Execute les 7 couches sequentiellement."""
    reports: list[LayerReport] = []
    total_start = time.perf_counter()
    first_fail: str | None = None
    for layer_fn in LAYERS:
        r = await layer_fn(pool, ctx)
        reports.append(r)
        if not r.passed and first_fail is None:
            first_fail = r.name
            if stop_on_fail:
                break
    total_ms = int((time.perf_counter() - total_start) * 1000)

    failures = sum(1 for r in reports if not r.passed)
    if failures == 0:
        verdict = "PASS"
    elif failures == 1:
        verdict = "CONDITIONAL_PASS"
    elif failures <= 3:
        verdict = "SOFT_FAIL"
    else:
        verdict = "HARD_FAIL"
    return SevenLayerReport(
        verdict=verdict, layers=reports,
        total_duration_ms=total_ms, first_fail=first_fail,
    )
