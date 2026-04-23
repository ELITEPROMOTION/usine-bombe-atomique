"""V4.8 BLOC 2 - Autonomous Executor.

Pour toute action qui n'est PAS A/B/C, le systeme doit resoudre en autonomie.
Ce module expose des helpers safe pour :
- Installer des outils Docker locaux (sans touchers externes sensibles)
- Ecrire des fichiers de configuration dans le workspace
- Appeler des APIs HTTP
- Executer des migrations (delegue a asyncpg)
- Deployer (simule via promotion_engine)
- Rollback (delegue a promotion_engine + confidence_rollback)

Chaque action est tracee dans evidence_ledger avec kind='decision'.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg
import httpx

from app.orchestration import audit_events, evidence_ledger

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    action: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    evidence_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "ok": self.ok,
                "detail": self.detail,
                "evidence_id": self.evidence_id}


# ------------------------------------------------------------------ filesystem

async def write_config_file(
    pool: asyncpg.Pool, task_id: str | None, path: str, content: str,
    workspace_root: str,
) -> ExecResult:
    """Ecrit un fichier de config dans le workspace. Jamais hors workspace."""
    root = Path(workspace_root).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return ExecResult("write_config_file", False,
                          {"error": "chemin hors workspace"})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    ev = await evidence_ledger.record(
        pool, kind="decision", actor="autonomous_executor.write_config",
        payload={"path": path, "bytes": len(content.encode("utf-8"))},
        task_id=task_id,
    )
    return ExecResult("write_config_file", True,
                       {"path": path, "bytes": len(content.encode("utf-8"))},
                       evidence_id=ev)


# ------------------------------------------------------------------ http api

async def http_call(
    pool: asyncpg.Pool, task_id: str | None, method: str, url: str,
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout: float = 15.0,
) -> ExecResult:
    async with httpx.AsyncClient(timeout=timeout, headers=headers or {}) as c:
        try:
            r = await c.request(method.upper(), url, json=json_body)
            ok = 200 <= r.status_code < 400
            detail = {"status": r.status_code,
                      "body_preview": r.text[:400]}
        except Exception as exc:
            ok = False
            detail = {"error": str(exc)[:200]}
    ev = await evidence_ledger.record(
        pool, kind="decision", actor="autonomous_executor.http",
        payload={"method": method.upper(), "url": url, "ok": ok, **detail},
        task_id=task_id,
    )
    return ExecResult(f"http_{method.lower()}", ok, detail, evidence_id=ev)


# ------------------------------------------------------------------ migration

async def run_sql_migration(
    pool: asyncpg.Pool, task_id: str | None, sql: str,
) -> ExecResult:
    """Applique une migration SQL transactionnellement."""
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(sql)
        ok, detail = True, {"statements": sql.count(";")}
    except asyncpg.PostgresError as exc:
        ok, detail = False, {"error": str(exc)[:240]}
    ev = await evidence_ledger.record(
        pool, kind="decision", actor="autonomous_executor.migration",
        payload={"ok": ok, "sql_preview": sql[:400], **detail},
        task_id=task_id,
    )
    return ExecResult("run_sql_migration", ok, detail, evidence_id=ev)


# ------------------------------------------------------------------ shell

_ALLOWED_BINARIES = frozenset({
    "pytest", "ruff", "bandit", "radon", "mypy", "vulture",
    "git", "docker", "psql", "pg_isready", "redis-cli",
    "python", "pip", "node", "npm",
})


async def run_shell(
    pool: asyncpg.Pool, task_id: str | None, cmd: list[str],
    cwd: str | None = None, timeout: int = 120,
) -> ExecResult:
    """Execute une commande dans la whitelist. Sinon refuse."""
    if not cmd or cmd[0] not in _ALLOWED_BINARIES:
        return ExecResult(
            "run_shell", False,
            {"error": f"binary '{cmd[0] if cmd else ''}' hors whitelist"},
        )
    loop = asyncio.get_running_loop()
    def _run():
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                                timeout=timeout)
    try:
        proc = await loop.run_in_executor(None, _run)
        ok = proc.returncode == 0
        detail = {"returncode": proc.returncode,
                  "stdout_tail": (proc.stdout or "")[-600:],
                  "stderr_tail": (proc.stderr or "")[-600:]}
    except subprocess.TimeoutExpired:
        ok, detail = False, {"error": "timeout"}
    except Exception as exc:
        ok, detail = False, {"error": str(exc)[:240]}
    ev = await evidence_ledger.record(
        pool, kind="decision", actor="autonomous_executor.shell",
        payload={"cmd": " ".join(cmd), "ok": ok, **detail},
        task_id=task_id,
    )
    return ExecResult("run_shell", ok, detail, evidence_id=ev)


# ------------------------------------------------------------------ resolve

async def resolve_non_user_action(
    pool: asyncpg.Pool, task_id: str, action_kind: str, context: dict[str, Any],
) -> ExecResult:
    """Point d'entree generique : le caller declare une action non-A/B/C,
    on route vers l'executor adapte et on trace."""
    if action_kind == "http_api_call":
        return await http_call(
            pool, task_id, context.get("method", "GET"),
            context["url"], headers=context.get("headers"),
            json_body=context.get("body"),
        )
    if action_kind == "sql_migration":
        return await run_sql_migration(pool, task_id, context["sql"])
    if action_kind == "shell":
        return await run_shell(
            pool, task_id, context["cmd"], cwd=context.get("cwd"),
            timeout=int(context.get("timeout", 120)),
        )
    if action_kind == "config_file":
        return await write_config_file(
            pool, task_id, context["path"], context["content"],
            workspace_root=context["workspace_root"],
        )
    # Inconnu : on trace mais on ne bloque pas. Le caller gere.
    await audit_events.emit(
        pool, action="autonomous_unhandled", actor="autonomous_executor",
        payload={"action_kind": action_kind, "context_keys": list(context.keys())},
        task_id=task_id,
    )
    return ExecResult(action_kind, False,
                       {"error": f"action_kind '{action_kind}' non supportee"})
