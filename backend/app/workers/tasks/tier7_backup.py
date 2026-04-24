"""Tier 7 - Backup database (2x/jour)."""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from ._base import workflow_task


@workflow_task("task_backup_database", timeout_s=900)
async def task_backup_database(_ctx: dict[str, Any] | None = None,
                                **_: Any) -> dict[str, Any]:
    """Execute pg_dump via asyncio subprocess.

    Fallback : enregistre metadata si pg_dump absent.
    """
    from app.config import get_settings
    s = get_settings()
    out_dir_env = os.environ.get("UBA_BACKUP_DIR")
    out_dir = Path(out_dir_env) if out_dir_env else Path(tempfile.mkdtemp(prefix="uba_bk_"))
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_file = out_dir / f"uba_{ts}.sql"
    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        return {"backed_up": False, "reason": "pg_dump not installed",
                "target": str(out_file)}
    env = dict(os.environ)
    env["PGPASSWORD"] = s.POSTGRES_PASSWORD
    try:
        with open(out_file, "w", encoding="utf-8") as fh:
            proc = await asyncio.create_subprocess_exec(
                pg_dump, "-h", s.POSTGRES_HOST, "-p", str(s.POSTGRES_PORT),
                "-U", s.POSTGRES_USER, "-d", s.POSTGRES_DB, "--no-owner",
                stdout=fh, stderr=asyncio.subprocess.PIPE, env=env,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=800)
        if proc.returncode != 0:
            return {"backed_up": False,
                    "error": stderr.decode("utf-8", errors="ignore")[:500]}
        return {"backed_up": True, "path": str(out_file),
                "size_bytes": out_file.stat().st_size}
    except Exception as exc:
        return {"backed_up": False, "error": str(exc)[:300]}


ALL_TASKS = [
    task_backup_database,
]
