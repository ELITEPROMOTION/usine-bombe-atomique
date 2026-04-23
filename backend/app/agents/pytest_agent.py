"""Agent #04 Pytest - execute la suite pytest du workspace et analyse le rapport.

Utilise `pytest-json-report` pour obtenir une sortie machine-parsable.
Score = passed / max(total, 1) ; passe si score >= 0.90 et aucun erreur fatale.
Si aucun test n'est trouve, score = 0 et passed=False (la V1 exige des tests).
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace

logger = logging.getLogger(__name__)


class PytestAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-04-pytest", name="Pytest Runner", version="1.0.0")
        self.category = "testing"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        report_path = workspace.root / ".pytest_report.json"
        returncode, stderr = await _run_pytest(workspace.root, report_path)
        report = _load_report(report_path)

        summary = report.get("summary", {}) if report else {}
        total = int(summary.get("total", 0))
        passed = int(summary.get("passed", 0))
        failed = int(summary.get("failed", 0))
        errors = int(summary.get("error", 0))
        collected = int(report.get("collected", 0)) if report else 0

        if total == 0 and collected == 0:
            score = 0.0
            ok = False
        else:
            score = passed / max(total, 1)
            ok = score >= 0.90 and failed == 0 and errors == 0

        return {
            "score": round(score, 3),
            "passed": ok,
            "tests_total": total,
            "tests_passed": passed,
            "tests_failed": failed,
            "errors": errors,
            "returncode": returncode,
            "stderr_tail": stderr[-500:] if stderr else "",
        }


async def _run_pytest(root: Path, report_path: Path) -> tuple[int, str]:
    env_cmd = [
        "pytest",
        str(root),
        "-q",
        "--json-report",
        f"--json-report-file={report_path}",
        "--no-header",
    ]
    proc = await asyncio.create_subprocess_exec(
        *env_cmd,
        cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    return proc.returncode or 0, (stderr or b"").decode("utf-8", errors="replace")


def _load_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("pytest json report invalid at %s", path)
        return None
