"""Agent #02 SonarQube - analyse qualite/securite.

V4.3 : tentative d'appel au serveur SonarQube CE (port 9000) en premier
lieu. Fallback automatique sur bandit+radon si le serveur ne repond pas.
Le score composite agrege les deux sources quand disponibles.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace
from app.integrations.sonarqube_client import SonarQubeClient, score_from_measures

logger = logging.getLogger(__name__)

PENALTY = {"HIGH": 0.30, "MEDIUM": 0.05, "LOW": 0.005}


class SonarQubeAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-02-sonarqube", name="SonarQube", version="1.0.0")
        self.category = "testing"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        task_id = inputs.get("task_id", "demo")

        # 1. Sonde locale (toujours executee : pas de dependance externe)
        bandit_issues = await _run_bandit(workspace.root)
        complexity = await _run_radon(workspace.root)

        severity_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
        for issue in bandit_issues:
            sev = (issue.get("issue_severity") or "LOW").upper()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        local_score = 1.0
        for sev, count in severity_counts.items():
            local_score -= PENALTY.get(sev, 0.0) * count
        avg_cc = complexity.get("average_complexity", 0.0)
        if avg_cc > 10:
            local_score -= 0.05 * ((avg_cc - 10) // 5 + 1)
        local_score = max(0.0, min(1.0, local_score))

        # 2. Tentative SonarQube (si serveur joignable)
        remote = {}
        remote_score: float | None = None
        client = SonarQubeClient()
        health = await client.health()
        if health.get("status") == "UP":
            project_key = f"uba-{task_id[:8]}"
            await client.ensure_project(project_key, f"UBA task {task_id[:8]}")
            measures = await client.measures(project_key)
            if measures:
                remote_score = score_from_measures(measures)
                remote = {"measures": measures, "score": remote_score}

        # 3. Score composite : moyenne si les deux disponibles
        score = (local_score + remote_score) / 2.0 if remote_score is not None else local_score

        passed = severity_counts["HIGH"] == 0 and score >= 0.70

        return {
            "score": round(score, 3),
            "passed": passed,
            "local_score": round(local_score, 3),
            "remote_score": round(remote_score, 3) if remote_score is not None else None,
            "sonarqube_status": health.get("status", "unknown"),
            "severity_counts": severity_counts,
            "issues": bandit_issues,
            "complexity": complexity,
            "sonarqube_remote": remote,
        }


async def _run_bandit(root: Path) -> list[dict[str, Any]]:
    # Exclude tests (pratique standard : bandit flag asserts = B101 sur tous les tests)
    proc = await asyncio.create_subprocess_exec(
        "bandit", "-q", "-r", str(root), "-f", "json", "--exit-zero",
        "-x", f"{root}/tests,{root}/.pytest_cache",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        payload = json.loads(stdout or b"{}")
    except json.JSONDecodeError:
        logger.warning("bandit output not JSON-parseable")
        return []
    return payload.get("results", [])


async def _run_radon(root: Path) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        "radon", "cc", "-s", "-j", str(root),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    try:
        per_file = json.loads(stdout or b"{}")
    except json.JSONDecodeError:
        return {"average_complexity": 0.0, "files_analyzed": 0}
    scores: list[int] = []
    for blocks in per_file.values():
        if isinstance(blocks, list):
            scores.extend(b.get("complexity", 0) for b in blocks if isinstance(b, dict))
    avg = sum(scores) / len(scores) if scores else 0.0
    return {
        "average_complexity": round(avg, 2),
        "files_analyzed": len(per_file),
        "blocks_analyzed": len(scores),
    }
