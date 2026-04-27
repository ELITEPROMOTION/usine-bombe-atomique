"""Agent #04 Pytest - execute la suite pytest du workspace et analyse le rapport.

V8.5 : robuste a l'absence du plugin `pytest-json-report`.

Path heureux :
  pytest --json-report --json-report-file=<path>
  -> on lit le JSON et on calcule score = passed / max(total, 1).

Fallback (V8.5) :
  Si pytest exit code in {2, 4} ET stderr contient "unrecognized arguments"
  (== plugin pytest-json-report absent), on relance pytest sans le flag
  json-report et on parse stdout pour extraire `X passed, Y failed`.
  Score calcule de la meme facon.

Score = passed / max(total, 1) ; ok si score >= 0.90 et 0 failed/errors.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace

logger = logging.getLogger(__name__)


class PytestAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-04-pytest", name="Pytest Runner", version="2.0.0")
        self.category = "testing"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        report_path = workspace.root / ".pytest_report.json"
        returncode, stdout, stderr = await _run_pytest_with_json(workspace.root, report_path)
        report = _load_report(report_path)
        used_fallback = False

        if report is None and _is_unrecognized_args(returncode, stderr):
            logger.warning(
                "pytest-json-report plugin absent (rc=%s) — fallback to stdout parser",
                returncode,
            )
            returncode, stdout, stderr = await _run_pytest_no_json(workspace.root)
            report = None
            used_fallback = True

        if report is not None:
            summary = report.get("summary", {}) or {}
            total = int(summary.get("total", 0))
            passed = int(summary.get("passed", 0))
            failed = int(summary.get("failed", 0))
            errors = int(summary.get("error", 0))
            collected = int(summary.get("collected", report.get("collected", 0) or 0))
        else:
            parsed = _parse_pytest_stdout(stdout)
            total = parsed["total"]
            passed = parsed["passed"]
            failed = parsed["failed"]
            errors = parsed["errors"]
            collected = total

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
            "used_fallback_parser": used_fallback,
            "stderr_tail": (stderr or "")[-500:],
        }


async def _run_pytest_with_json(root: Path, report_path: Path) -> tuple[int, str, str]:
    return await _exec_pytest(root, [
        "pytest", str(root), "-q",
        "--json-report", f"--json-report-file={report_path}",
        "--no-header",
    ])


async def _run_pytest_no_json(root: Path) -> tuple[int, str, str]:
    return await _exec_pytest(root, ["pytest", str(root), "-q", "--no-header"])


async def _exec_pytest(root: Path, cmd: list[str]) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    return (
        proc.returncode or 0,
        (stdout_b or b"").decode("utf-8", errors="replace"),
        (stderr_b or b"").decode("utf-8", errors="replace"),
    )


def _is_unrecognized_args(returncode: int, stderr: str) -> bool:
    if returncode not in (2, 4):
        return False
    return "unrecognized arguments" in (stderr or "").lower()


_RE_SUMMARY = re.compile(
    r"(?:^|\s)"
    r"(?:(?P<failed>\d+)\s+failed[,\s])?"
    r"(?:(?P<passed>\d+)\s+passed)?"
    r"(?:[,\s]+(?P<errors>\d+)\s+error)?",
    re.MULTILINE,
)
_RE_NUM = re.compile(r"(\d+)\s+(passed|failed|error|errors)")
_RE_NO_TESTS = re.compile(r"no tests ran", re.IGNORECASE)


def _parse_pytest_stdout(stdout: str) -> dict[str, int]:
    """Parse pytest summary in verbose (`=== X passed in Y ===`) AND quiet
    (`X passed in Y`) modes."""
    counts = {"passed": 0, "failed": 0, "errors": 0}
    if not stdout:
        return {**counts, "total": 0}

    if _RE_NO_TESTS.search(stdout):
        return {"passed": 0, "failed": 0, "errors": 0, "total": 0}

    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if " in " not in line:
            continue
        if not (line.startswith("=") or _RE_NUM.search(line)):
            continue
        for num, label in _RE_NUM.findall(line):
            label_norm = "errors" if label.startswith("error") else label
            counts[label_norm] = counts.get(label_norm, 0) + int(num)
        if any(counts.values()):
            break

    counts["total"] = counts["passed"] + counts["failed"] + counts["errors"]
    return counts


def _load_report(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("pytest json report invalid at %s", path)
        return None
