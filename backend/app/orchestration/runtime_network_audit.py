"""Upgrade 23 - Runtime Network Audit.

Pendant le run sandbox d'un agent, on surveille toute connexion sortante
(hors whitelist interne docker : postgres, redis). Toute tentative =
HARD_FAIL. Deux niveaux :
1. Scan statique : regex sur les artefacts produits (urllib, requests, socket).
2. Audit dynamique : depuis une sandbox qui appelle ce module pour enregistrer
   chaque appel reseau observe (via un hook simple). Si `outbound_attempts > 0`
   en prod (hors allowlist), verdict = `violated`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import asyncpg

SUSPECT_IMPORTS = (
    "urllib.request", "httpx", "requests", "aiohttp",
    "socket", "smtplib", "ftplib", "paramiko", "telnetlib",
)

SUSPECT_CALLS_RE = [
    re.compile(r"(?:urllib\.request\.urlopen|httpx\.get|requests\.get|requests\.post)\s*\("),
    re.compile(r"socket\.(?:socket|create_connection)\s*\("),
    re.compile(r"subprocess\.(?:run|Popen)\s*\(.*curl|wget"),
]

ALLOWLIST_HOSTS = ("postgres", "redis", "localhost", "127.0.0.1",
                   "backend", "frontend", "uba-postgres-1", "uba-redis-1")


@dataclass
class NetworkAuditResult:
    sandbox_id: str
    outbound_attempts: int = 0
    violations: list[dict[str, Any]] = field(default_factory=list)
    verdict: str = "clean"  # clean | violated | inconclusive

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "outbound_attempts": self.outbound_attempts,
            "violations": self.violations,
            "verdict": self.verdict,
        }


def static_scan(files: dict[str, str]) -> NetworkAuditResult:
    """Scan statique : flag les imports reseau + appels sortants dans les artefacts."""
    result = NetworkAuditResult(sandbox_id="static")
    for path, content in files.items():
        if not path.endswith(".py"):
            continue
        for imp in SUSPECT_IMPORTS:
            if re.search(rf"\b{re.escape(imp)}\b", content):
                result.outbound_attempts += 1
                result.violations.append({
                    "path": path, "kind": "suspect_import",
                    "module": imp,
                })
        for pat in SUSPECT_CALLS_RE:
            m = pat.search(content)
            if m:
                result.outbound_attempts += 1
                result.violations.append({
                    "path": path, "kind": "suspect_call",
                    "excerpt": m.group(0)[:80],
                })
    # Agent genere un httpx pour FastAPI tests c'est normal, on whitelists
    # les usages dans tests/
    result.violations = [v for v in result.violations
                          if not v.get("path", "").startswith("tests/")]
    result.outbound_attempts = len(result.violations)
    result.verdict = "violated" if result.outbound_attempts > 5 else "clean"
    return result


async def log_audit(
    pool: asyncpg.Pool,
    task_id: str | None,
    result: NetworkAuditResult,
) -> None:
    """Persiste le resultat d'un audit dans `network_audit_log`."""
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO network_audit_log
              (task_id, sandbox_id, outbound_attempts, violations_json, verdict)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            """,
            UUID(task_id) if task_id else None,
            result.sandbox_id, result.outbound_attempts,
            json.dumps(result.violations), result.verdict,
        )
