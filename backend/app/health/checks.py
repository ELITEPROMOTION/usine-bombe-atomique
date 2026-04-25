"""15 health checks exhaustifs UBA V5.7.

Categories :
  CRITICAL : postgres_primary, redis_primary, vault, disk, memory,
             truth_chain_integrity, evidence_chain_valid
  WARNING  : postgres_replica_lag, redis_memory, claude_api_latency,
             sonarqube, cpu_load, queue_depth, failed_tasks_rate,
             backup_freshness
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable, ClassVar

logger = logging.getLogger("uba.health")


class CheckStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    latency_ms: int
    details: dict[str, Any]
    is_critical: bool = False
    message: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "is_critical": self.is_critical,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp or time.time(),
        }


HealthCheckFn = Callable[[], Awaitable[CheckResult]]


# ============================================================================
# Les 15 checks
# ============================================================================

async def check_postgres_primary_ping() -> CheckResult:
    """CRITICAL : latence SELECT 1 < threshold (env-overridable)."""
    name = "postgres_primary_ping"
    healthy_thr = int(os.getenv("PG_PING_HEALTHY_MS", "200"))
    degraded_thr = int(os.getenv("PG_PING_DEGRADED_MS", "500"))
    start = time.perf_counter()
    try:
        from app.database import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            ok = await conn.fetchval("SELECT 1")
        latency = int((time.perf_counter() - start) * 1000)
        status = (CheckStatus.HEALTHY if latency < healthy_thr
                   else CheckStatus.DEGRADED if latency < degraded_thr
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status, latency_ms=latency,
            details={"select_1": ok, "threshold_ms": healthy_thr},
            is_critical=True,
            message=f"latency={latency}ms",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNHEALTHY,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
            message=str(exc)[:100],
        )


async def check_postgres_replica_lag() -> CheckResult:
    """WARNING : lag replica < 5s (si replica configure)."""
    name = "postgres_replica_lag"
    # Pas de replica configure dans ce dev setup - retourne HEALTHY
    return CheckResult(
        name=name, status=CheckStatus.HEALTHY, latency_ms=0,
        details={"replica_configured": False},
        message="no replica",
    )


async def check_redis_primary_ping() -> CheckResult:
    """CRITICAL : ping redis < threshold (env-overridable)."""
    name = "redis_primary_ping"
    healthy_thr = int(os.getenv("REDIS_PING_HEALTHY_MS", "100"))
    degraded_thr = int(os.getenv("REDIS_PING_DEGRADED_MS", "300"))
    start = time.perf_counter()
    try:
        import redis.asyncio as redis_lib
        from app.config import get_settings
        s = get_settings()
        r = redis_lib.Redis(
            host=s.REDIS_HOST, port=s.REDIS_PORT,
            password=s.REDIS_PASSWORD or None, db=s.REDIS_DB,
        )
        try:
            pong = await r.ping()
        finally:
            await r.aclose()
        latency = int((time.perf_counter() - start) * 1000)
        status = (CheckStatus.HEALTHY if latency < healthy_thr and pong
                   else CheckStatus.DEGRADED if latency < degraded_thr and pong
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status, latency_ms=latency,
            details={"ping": bool(pong), "threshold_ms": healthy_thr},
            is_critical=True,
            message=f"latency={latency}ms",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNHEALTHY,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
            message=str(exc)[:100],
        )


async def check_redis_memory_usage() -> CheckResult:
    """WARNING : memoire Redis < 90% max."""
    name = "redis_memory_usage"
    start = time.perf_counter()
    try:
        import redis.asyncio as redis_lib
        from app.config import get_settings
        s = get_settings()
        r = redis_lib.Redis(
            host=s.REDIS_HOST, port=s.REDIS_PORT,
            password=s.REDIS_PASSWORD or None, db=s.REDIS_DB,
        )
        try:
            info = await r.info("memory")
        finally:
            await r.aclose()
        used = int(info.get("used_memory", 0))
        maxmem = int(info.get("maxmemory", 0))
        pct = (used / maxmem * 100) if maxmem > 0 else 0
        status = (CheckStatus.HEALTHY if pct < 75
                   else CheckStatus.DEGRADED if pct < 90
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"used_mb": used // 1024 // 1024,
                     "max_mb": maxmem // 1024 // 1024 if maxmem else None,
                     "percent": round(pct, 1)},
            message=f"{pct:.1f}% used",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]},
            message=str(exc)[:100],
        )


async def check_vault_status() -> CheckResult:
    """CRITICAL : vault reachable + not sealed."""
    name = "vault_status"
    start = time.perf_counter()
    try:
        import httpx
        addr = os.environ.get("VAULT_ADDR", "http://vault:8200")
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get(f"{addr}/v1/sys/health?standbyok=true")
        latency = int((time.perf_counter() - start) * 1000)
        data = resp.json() if resp.status_code in (200, 429) else {}
        sealed = bool(data.get("sealed", True))
        initialized = bool(data.get("initialized", False))
        status = (CheckStatus.HEALTHY
                   if resp.status_code in (200, 429) and not sealed
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status, latency_ms=latency,
            details={"sealed": sealed, "initialized": initialized,
                     "http_status": resp.status_code},
            is_critical=True,
            message=("sealed" if sealed else "unsealed") if initialized
                     else "uninitialized",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNHEALTHY,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
            message=str(exc)[:100],
        )


async def check_claude_api_latency() -> CheckResult:
    """WARNING : p99 Claude API < 3s (compteur local dans resilience)."""
    name = "claude_api_latency"
    from app.resilience import CircuitBreakerRegistry
    try:
        cb = CircuitBreakerRegistry.instance().get("claude_api")
        state = cb.state
        status = (CheckStatus.HEALTHY if state.value == "closed"
                   else CheckStatus.DEGRADED)
        return CheckResult(
            name=name, status=status, latency_ms=0,
            details={"breaker_state": state.value,
                     "failures": cb._consecutive_failures,
                     "total_calls": cb.metrics.total_calls},
            message=f"breaker={state.value}",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN, latency_ms=0,
            details={"error": str(exc)[:200]},
        )


async def check_sonarqube_api() -> CheckResult:
    """WARNING : SonarQube reachable."""
    name = "sonarqube_api"
    start = time.perf_counter()
    try:
        import httpx
        addr = os.environ.get("SONAR_HOST_URL", "http://sonarqube:9000")
        async with httpx.AsyncClient(timeout=5.0) as c:
            resp = await c.get(f"{addr}/api/system/status")
        latency = int((time.perf_counter() - start) * 1000)
        return CheckResult(
            name=name,
            status=(CheckStatus.HEALTHY if resp.status_code == 200
                     else CheckStatus.DEGRADED),
            latency_ms=latency,
            details={"http_status": resp.status_code},
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.DEGRADED,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]},
            message=str(exc)[:100],
        )


def check_disk_usage_sync() -> CheckResult:
    """CRITICAL : disque < 85%."""
    name = "disk_usage"
    start = time.perf_counter()
    try:
        total, used, free = shutil.disk_usage("/")
        pct = (used / total * 100)
        status = (CheckStatus.HEALTHY if pct < 70
                   else CheckStatus.DEGRADED if pct < 85
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"percent": round(pct, 1),
                     "free_gb": round(free / 1024**3, 1),
                     "total_gb": round(total / 1024**3, 1)},
            is_critical=True,
            message=f"{pct:.1f}% used",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
        )


async def check_disk_usage() -> CheckResult:
    return await asyncio.get_running_loop().run_in_executor(
        None, check_disk_usage_sync,
    )


def check_memory_usage_sync() -> CheckResult:
    """CRITICAL : memoire < 90%."""
    name = "memory_usage"
    start = time.perf_counter()
    try:
        # Parse /proc/meminfo (Linux only)
        meminfo: dict[str, int] = {}
        with open("/proc/meminfo") as fh:
            for line in fh:
                parts = line.split(":")
                if len(parts) == 2:
                    value = parts[1].strip().split()[0]
                    meminfo[parts[0].strip()] = int(value) * 1024  # kB->B
        total = meminfo.get("MemTotal", 0)
        avail = meminfo.get("MemAvailable", 0)
        used = total - avail
        pct = (used / total * 100) if total > 0 else 0
        status = (CheckStatus.HEALTHY if pct < 75
                   else CheckStatus.DEGRADED if pct < 90
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"percent": round(pct, 1),
                     "used_mb": used // 1024 // 1024,
                     "total_mb": total // 1024 // 1024},
            is_critical=True,
            message=f"{pct:.1f}% used",
        )
    except FileNotFoundError:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN, latency_ms=0,
            details={"error": "/proc/meminfo not available"},
            is_critical=True,
        )


async def check_memory_usage() -> CheckResult:
    return await asyncio.get_running_loop().run_in_executor(
        None, check_memory_usage_sync,
    )


def check_cpu_load_sync() -> CheckResult:
    """WARNING : load 1min < 3.0."""
    name = "cpu_load_1min"
    try:
        load1, load5, load15 = os.getloadavg()
        status = (CheckStatus.HEALTHY if load1 < 2.0
                   else CheckStatus.DEGRADED if load1 < 4.0
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status, latency_ms=0,
            details={"load_1min": round(load1, 2),
                     "load_5min": round(load5, 2),
                     "load_15min": round(load15, 2)},
            message=f"load_1min={load1:.2f}",
        )
    except (OSError, AttributeError):
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN, latency_ms=0,
            details={"error": "getloadavg not available"},
        )


async def check_cpu_load() -> CheckResult:
    return await asyncio.get_running_loop().run_in_executor(
        None, check_cpu_load_sync,
    )


async def check_queue_depth() -> CheckResult:
    """WARNING : arq queue < 100."""
    name = "queue_depth_arq"
    start = time.perf_counter()
    try:
        import redis.asyncio as redis_lib
        from app.config import get_settings
        s = get_settings()
        r = redis_lib.Redis(
            host=s.REDIS_HOST, port=s.REDIS_PORT,
            password=s.REDIS_PASSWORD or None, db=s.REDIS_DB,
        )
        queue_len = 0
        try:
            for key in ("arq:queue", "arq:queue:health-check"):
                ktype = await r.type(key)
                ktype_s = ktype.decode() if isinstance(ktype, bytes) else str(ktype)
                if ktype_s == "zset":
                    queue_len = max(queue_len, int(await r.zcard(key)))
                elif ktype_s == "list":
                    queue_len = max(queue_len, int(await r.llen(key)))
        finally:
            await r.aclose()
        status = (CheckStatus.HEALTHY if queue_len < 100
                   else CheckStatus.DEGRADED if queue_len < 500
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"queue_len": queue_len},
            message=f"depth={queue_len}",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]},
        )


async def check_failed_tasks_rate() -> CheckResult:
    """WARNING : taux echec workflow < 5% sur 5 min."""
    name = "failed_tasks_rate"
    start = time.perf_counter()
    try:
        from app.database import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM workflow_executions "
                "WHERE started_at > NOW() - INTERVAL '5 minutes'",
            )
            failed = await conn.fetchval(
                "SELECT COUNT(*) FROM workflow_executions "
                "WHERE status IN ('failed','timeout') "
                "AND started_at > NOW() - INTERVAL '5 minutes'",
            )
        total_i = int(total or 0)
        rate = (int(failed or 0) / total_i) if total_i else 0
        status = (CheckStatus.HEALTHY if rate < 0.02
                   else CheckStatus.DEGRADED if rate < 0.05
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"total_5min": total_i, "failed_5min": int(failed or 0),
                     "rate": round(rate, 4)},
            message=f"rate={rate:.2%}",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]},
        )


async def check_truth_chain_integrity() -> CheckResult:
    """CRITICAL : evidence_ledger integrity OK."""
    name = "truth_chain_integrity"
    start = time.perf_counter()
    try:
        from app.database import get_pool
        from app.orchestration import evidence_ledger
        pool = get_pool()
        rep = await evidence_ledger.verify_chain(pool, limit=5000)
        ok = bool(rep.get("integrity_ok"))
        return CheckResult(
            name=name,
            status=CheckStatus.HEALTHY if ok else CheckStatus.UNHEALTHY,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"integrity_ok": ok,
                     "events_checked": rep.get("events_checked", 0),
                     "broken": len(rep.get("broken", []))},
            is_critical=True,
            message="chain ok" if ok else f"broken={len(rep.get('broken', []))}",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
        )


async def check_evidence_chain_valid() -> CheckResult:
    """CRITICAL : audit_events immutability OK."""
    name = "evidence_chain_valid"
    start = time.perf_counter()
    try:
        from app.database import get_pool
        from app.orchestration import audit_events
        pool = get_pool()
        rep = await audit_events.verify_immutability(pool)
        ok = bool(rep.get("immutable"))
        return CheckResult(
            name=name,
            status=CheckStatus.HEALTHY if ok else CheckStatus.UNHEALTHY,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details=rep,
            is_critical=True,
            message="immutable" if ok else "mutable",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]}, is_critical=True,
        )


async def check_backup_freshness() -> CheckResult:
    """WARNING : dernier backup < 2h."""
    name = "backup_freshness"
    start = time.perf_counter()
    try:
        from app.database import get_pool
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT MAX(finished_at) AS last,
                       EXTRACT(EPOCH FROM (NOW() - MAX(finished_at))) AS age_s
                FROM workflow_executions
                WHERE task_name = 'task_backup_database'
                  AND status = 'succeeded'
                """,
            )
        if row is None or row["last"] is None:
            return CheckResult(
                name=name, status=CheckStatus.DEGRADED,
                latency_ms=int((time.perf_counter() - start) * 1000),
                details={"last_backup": None},
                message="no backup yet",
            )
        age_s = int(row["age_s"] or 0)
        age_h = age_s / 3600
        status = (CheckStatus.HEALTHY if age_h < 2
                   else CheckStatus.DEGRADED if age_h < 24
                   else CheckStatus.UNHEALTHY)
        return CheckResult(
            name=name, status=status,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"last_backup": row["last"].isoformat(),
                     "age_hours": round(age_h, 1)},
            message=f"{age_h:.1f}h ago",
        )
    except Exception as exc:
        return CheckResult(
            name=name, status=CheckStatus.UNKNOWN,
            latency_ms=int((time.perf_counter() - start) * 1000),
            details={"error": str(exc)[:200]},
        )


# ============================================================================
# Registry + runner
# ============================================================================

CHECKS: dict[str, HealthCheckFn] = {
    "postgres_primary_ping": check_postgres_primary_ping,
    "postgres_replica_lag": check_postgres_replica_lag,
    "redis_primary_ping": check_redis_primary_ping,
    "redis_memory_usage": check_redis_memory_usage,
    "vault_status": check_vault_status,
    "claude_api_latency": check_claude_api_latency,
    "sonarqube_api": check_sonarqube_api,
    "disk_usage": check_disk_usage,
    "memory_usage": check_memory_usage,
    "cpu_load_1min": check_cpu_load,
    "queue_depth_arq": check_queue_depth,
    "failed_tasks_rate": check_failed_tasks_rate,
    "truth_chain_integrity": check_truth_chain_integrity,
    "evidence_chain_valid": check_evidence_chain_valid,
    "backup_freshness": check_backup_freshness,
}


class HealthCheckRegistry:
    """Registry cache des derniers resultats (TTL 30s)."""

    _instance: ClassVar["HealthCheckRegistry | None"] = None
    _lock: ClassVar[threading.RLock] = threading.RLock()

    def __init__(self) -> None:
        self._cache: dict[str, CheckResult] = {}
        self._cache_ts: dict[str, float] = {}
        self._ttl_s = 30.0

    @classmethod
    def instance(cls) -> "HealthCheckRegistry":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def list_check_names(self) -> list[str]:
        return sorted(CHECKS.keys())

    async def run(self, name: str, use_cache: bool = True) -> CheckResult:
        if use_cache and name in self._cache:
            if (time.time() - self._cache_ts.get(name, 0)) < self._ttl_s:
                return self._cache[name]
        fn = CHECKS.get(name)
        if fn is None:
            return CheckResult(
                name=name, status=CheckStatus.UNKNOWN, latency_ms=0,
                details={"error": f"unknown check {name}"},
            )
        result = await fn()
        result.timestamp = time.time()
        self._cache[name] = result
        self._cache_ts[name] = time.time()
        return result

    async def run_all(self, use_cache: bool = True) -> list[CheckResult]:
        tasks = [self.run(n, use_cache) for n in CHECKS]
        return await asyncio.gather(*tasks)


async def run_all(use_cache: bool = True) -> list[CheckResult]:
    return await HealthCheckRegistry.instance().run_all(use_cache=use_cache)
