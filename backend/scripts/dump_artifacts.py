"""One-shot : dump tous les artefacts d'une tache vers /out (monte en volume).

Usage (dans le container backend) :
    TASK_ID=xxxx OUT_DIR=/out python scripts/dump_artifacts.py
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from app.config import get_settings


async def main() -> None:
    task_id = os.environ["TASK_ID"]
    out_dir = Path(os.environ.get("OUT_DIR", "/out"))
    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.postgres_dsn)
    try:
        rows = await conn.fetch(
            "SELECT path, content FROM artifacts WHERE task_id = $1 ORDER BY path",
            task_id,
        )
    finally:
        await conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for row in rows:
        rel = row["path"]
        target = out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(row["content"] or "", encoding="utf-8")
        count += 1
    print(f"Wrote {count} files under {out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
