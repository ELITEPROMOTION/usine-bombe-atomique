"""Agent #14 Code Linter - execute ruff sur l'espace de travail.

Sortie normalisee : liste d'issues + score = 1 - 0.01 * min(issues, 100).
Passe si score >= 0.80.
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


class LinterAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-14-linter", name="Code Linter", version="1.0.0")
        self.category = "testing"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        issues = await _run_ruff(workspace.root)
        score = max(0.0, 1.0 - 0.01 * min(len(issues), 100))
        passed = score >= 0.80
        by_code: dict[str, int] = {}
        for issue in issues:
            code = issue.get("code") or "UNK"
            by_code[code] = by_code.get(code, 0) + 1
        return {
            "score": round(score, 3),
            "passed": passed,
            "issues_count": len(issues),
            "issues_by_code": by_code,
            "issues": issues[:50],
        }


async def _run_ruff(root: Path) -> list[dict[str, Any]]:
    proc = await asyncio.create_subprocess_exec(
        "ruff", "check", str(root), "--output-format", "json", "--exit-zero",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        data = json.loads(stdout or b"[]")
    except json.JSONDecodeError:
        logger.warning("ruff output not JSON-parseable")
        return []
    if not isinstance(data, list):
        return []
    return data
