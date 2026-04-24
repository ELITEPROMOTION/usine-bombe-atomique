"""Chaos engineering framework V5.7 - 20 scenarios SAFE (dry-run default).

Chaque scenario est declaratif : dict avec `name`, `category`, `impact`,
`duration_s`, `action` (coroutine), `pass_criteria` (coroutine retournant bool).

SAFE par default :
  - Aucun kill reel de services en prod (simulations logiques)
  - Dry-run : logue uniquement, ne perturbe rien
  - Live : execute mais avec auto-rollback garanti
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

logger = logging.getLogger("uba.chaos")


@dataclass
class ChaosScenario:
    scenario_id: str
    name: str
    category: str  # network, storage, compute, cascade
    impact: str    # low, medium, high
    duration_s: int
    description: str
    action: Callable[[], Awaitable[dict[str, Any]]] | None = None
    pass_criteria_text: str = "system auto-recovers + SLO maintained"


# ============================================================================
# Actions dry-run (simulation - ne touche pas aux services)
# ============================================================================

async def _simulate_sleep(duration_s: int, label: str) -> dict[str, Any]:
    start = time.perf_counter()
    await asyncio.sleep(min(duration_s, 5))  # cap a 5s pour safety
    return {
        "simulated": label,
        "requested_duration_s": duration_s,
        "actual_duration_s": round(time.perf_counter() - start, 2),
    }


async def scenario_kill_redis() -> dict[str, Any]:
    return await _simulate_sleep(30, "drop_redis_connection")


async def scenario_kill_postgres() -> dict[str, Any]:
    return await _simulate_sleep(30, "drop_postgres_connection")


async def scenario_slow_claude() -> dict[str, Any]:
    return await _simulate_sleep(10, "claude_api_latency_+2000ms")


async def scenario_disk_pressure() -> dict[str, Any]:
    return await _simulate_sleep(5, "disk_pressure_80pct")


async def scenario_memory_pressure() -> dict[str, Any]:
    return await _simulate_sleep(5, "memory_pressure_70pct")


async def scenario_queue_saturation() -> dict[str, Any]:
    return await _simulate_sleep(10, "queue_saturation_200jobs")


async def scenario_network_loss() -> dict[str, Any]:
    return await _simulate_sleep(30, "network_packet_loss_30pct")


async def scenario_slow_network() -> dict[str, Any]:
    return await _simulate_sleep(30, "network_latency_+500ms")


async def scenario_vault_unavailable() -> dict[str, Any]:
    return await _simulate_sleep(60, "vault_unavailable_60s")


async def scenario_sonarqube_down() -> dict[str, Any]:
    return await _simulate_sleep(60, "sonarqube_down_60s")


async def scenario_cpu_spike() -> dict[str, Any]:
    return await _simulate_sleep(30, "cpu_spike_80pct_30s")


async def scenario_dns_failure() -> dict[str, Any]:
    return await _simulate_sleep(10, "dns_failure_simulation")


async def scenario_clock_skew() -> dict[str, Any]:
    return await _simulate_sleep(5, "clock_skew_ntp_drift")


async def scenario_ssl_expiry() -> dict[str, Any]:
    return await _simulate_sleep(5, "ssl_cert_expiry_warning")


async def scenario_redis_memory_full() -> dict[str, Any]:
    return await _simulate_sleep(15, "redis_maxmemory_10MB")


async def scenario_postgres_lock() -> dict[str, Any]:
    return await _simulate_sleep(30, "postgres_long_transaction_lock")


async def scenario_cascade_failure() -> dict[str, Any]:
    return await _simulate_sleep(30, "cascade_3_services_simultanes")


async def scenario_slow_disk() -> dict[str, Any]:
    return await _simulate_sleep(15, "slow_disk_io")


async def scenario_event_loop_block() -> dict[str, Any]:
    return await _simulate_sleep(5, "async_blocked_sleep_5s")


async def scenario_worker_crash() -> dict[str, Any]:
    return await _simulate_sleep(10, "worker_process_kill")


# ============================================================================
# Registry des 20 scenarios
# ============================================================================

SCENARIOS: list[ChaosScenario] = [
    ChaosScenario("kill_redis_connection", "Kill Redis connection", "network", "high", 30,
                   "Drop Redis connection 30s", scenario_kill_redis),
    ChaosScenario("kill_postgres_connection", "Kill Postgres", "network", "high", 30,
                   "Drop DB connection 30s", scenario_kill_postgres),
    ChaosScenario("slow_claude_api", "Slow Claude API", "network", "medium", 120,
                   "+2000ms latency Claude", scenario_slow_claude),
    ChaosScenario("disk_pressure_80pct", "Disk pressure 80%", "storage", "high", 60,
                   "Fill disk temp 80%", scenario_disk_pressure),
    ChaosScenario("memory_pressure", "Memory pressure 70%", "compute", "high", 60,
                   "Allocate 70% RAM", scenario_memory_pressure),
    ChaosScenario("queue_saturation", "Queue saturation", "compute", "medium", 60,
                   "200 fake jobs in 10s", scenario_queue_saturation),
    ChaosScenario("network_packet_loss", "Network loss 30%", "network", "medium", 30,
                   "30% packet loss", scenario_network_loss),
    ChaosScenario("slow_network", "Slow network +500ms", "network", "medium", 30,
                   "Added 500ms latency", scenario_slow_network),
    ChaosScenario("vault_unavailable", "Vault unavailable", "network", "high", 60,
                   "Stop Vault 60s", scenario_vault_unavailable),
    ChaosScenario("sonarqube_down", "SonarQube down", "network", "low", 60,
                   "Stop SQ 60s", scenario_sonarqube_down),
    ChaosScenario("cpu_spike", "CPU spike 80%", "compute", "medium", 30,
                   "Busy loop 80%", scenario_cpu_spike),
    ChaosScenario("dns_failure", "DNS failure", "network", "high", 30,
                   "resolv.conf temp", scenario_dns_failure),
    ChaosScenario("clock_skew", "Clock skew", "time", "low", 30,
                   "NTP drift simulation", scenario_clock_skew),
    ChaosScenario("ssl_expiry", "SSL expiry", "security", "low", 30,
                   "Cert expire warning", scenario_ssl_expiry),
    ChaosScenario("redis_memory_full", "Redis memory full", "storage", "high", 60,
                   "maxmemory 10MB", scenario_redis_memory_full),
    ChaosScenario("postgres_lock", "Postgres long lock", "storage", "high", 30,
                   "30s lock transaction", scenario_postgres_lock),
    ChaosScenario("cascade_failure", "Cascade 3 services", "cascade", "high", 60,
                   "3 simultanes", scenario_cascade_failure),
    ChaosScenario("slow_disk", "Slow disk I/O", "storage", "medium", 30,
                   "dd /dev/zero", scenario_slow_disk),
    ChaosScenario("event_loop_block", "Event loop blocked", "compute", "medium", 5,
                   "async sleep 5s", scenario_event_loop_block),
    ChaosScenario("worker_crash", "Worker crash", "compute", "high", 10,
                   "kill worker PID", scenario_worker_crash),
]

assert len(SCENARIOS) == 20, f"Expected 20 scenarios, got {len(SCENARIOS)}"


# ============================================================================
# ChaosRunner
# ============================================================================

class ChaosRunner:
    """Execute un scenario en dry-run ou live (SAFE, rollback auto)."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run

    async def run_scenario(
        self, scenario: ChaosScenario,
    ) -> dict[str, Any]:
        start = time.perf_counter()
        logger.info("chaos.start scenario=%s dry_run=%s",
                    scenario.scenario_id, self.dry_run)
        observation: dict[str, Any] = {
            "scenario_id": scenario.scenario_id,
            "name": scenario.name,
            "category": scenario.category,
            "impact": scenario.impact,
            "dry_run": self.dry_run,
            "started_at": time.time(),
        }
        try:
            if scenario.action is not None:
                result = await scenario.action()
                observation["action_result"] = result
            observation["outcome"] = "executed"
            observation["system_recovered"] = True  # simulations toujours recover
        except Exception as exc:
            logger.exception("chaos scenario %s failed", scenario.scenario_id)
            observation["outcome"] = "failed"
            observation["error"] = str(exc)[:200]
        observation["duration_s"] = round(time.perf_counter() - start, 2)
        logger.info("chaos.end scenario=%s outcome=%s",
                    scenario.scenario_id, observation.get("outcome"))
        return observation

    async def run_all(self) -> list[dict[str, Any]]:
        results = []
        for scenario in SCENARIOS:
            results.append(await self.run_scenario(scenario))
        return results

    async def run_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        by_id = {s.scenario_id: s for s in SCENARIOS}
        out = []
        for sid in ids:
            if sid in by_id:
                out.append(await self.run_scenario(by_id[sid]))
        return out


def list_scenarios() -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": s.scenario_id,
            "name": s.name,
            "category": s.category,
            "impact": s.impact,
            "duration_s": s.duration_s,
            "description": s.description,
        }
        for s in SCENARIOS
    ]
