"""V8.5 — Quality Gates Engine.

Execute 6 gates strictes sur un projet livre par UBA AVANT que le ZIP final
ne soit produit. Si un gate FAIL, le pipeline doit re-generer (jusqu'a 3 fois)
ou abandonner avec un verdict precis.

Gates :
    1. LintGate          - ruff check (mode --quiet, fail si errors)
    2. PytestGate        - pytest -v ; tous PASS, exit 0
    3. CoverageGate      - pytest --cov ; >= 70% (proportionnel pour le score)
    4. DockerBuildGate   - docker build (skip si docker absent)
    5. DockerRunGate     - docker run + curl /health (skip si docker absent)
    6. ReadmeGate        - presence sections obligatoires + exemple curl

Chaque gate retourne un GateResult standardise. Les gates Docker sont
"skippable" (status=SKIP) si l'environnement n'a pas docker disponible —
ce n'est pas un FAIL, c'est une non-execution explicite tracee.

Persiste les resultats dans delivery_quality_gates (migration 035).
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GATE_LINT = "lint"
GATE_PYTEST = "pytest"
GATE_COVERAGE = "coverage"
GATE_DOCKER_BUILD = "docker_build"
GATE_DOCKER_RUN = "docker_run"
GATE_README = "readme"

GATE_ORDER = (
    GATE_LINT,
    GATE_PYTEST,
    GATE_COVERAGE,
    GATE_DOCKER_BUILD,
    GATE_DOCKER_RUN,
    GATE_README,
)

COVERAGE_MIN = 0.70
COVERAGE_TARGET = 0.80

README_REQUIRED_SECTIONS = (
    "description",
    "installation",
    "usage",
    "tests",
    "deploy",
    "license",
)


@dataclass
class GateResult:
    name: str
    status: str  # PASS | FAIL | SKIP | ERROR
    score: float = 0.0
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class GatesResult:
    overall_status: str  # PASS | FAIL
    gates: list[GateResult]

    @property
    def passed_count(self) -> int:
        return sum(1 for g in self.gates if g.status == "PASS")

    @property
    def failed_count(self) -> int:
        return sum(1 for g in self.gates if g.status == "FAIL")

    @property
    def skipped_count(self) -> int:
        return sum(1 for g in self.gates if g.status == "SKIP")

    @property
    def summary(self) -> str:
        return (
            f"{self.passed_count}/{len(self.gates)} PASS "
            f"({self.failed_count} FAIL, {self.skipped_count} SKIP)"
        )

    def first_failure(self) -> GateResult | None:
        return next((g for g in self.gates if g.status == "FAIL"), None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def validate_deliverable(
    project_path: Path,
    *,
    docker_available: bool | None = None,
    pytest_timeout_s: int = 120,
) -> GatesResult:
    """Execute les 6 gates sur project_path. Ne persiste rien."""
    project_path = Path(project_path).resolve()
    if docker_available is None:
        docker_available = _docker_available()

    gates: list[GateResult] = []
    gates.append(await _run_lint(project_path))
    gates.append(await _run_pytest(project_path, timeout_s=pytest_timeout_s))
    gates.append(await _run_coverage(project_path, timeout_s=pytest_timeout_s))
    gates.append(await _run_docker_build(project_path, docker_available))
    gates.append(await _run_docker_run(project_path, docker_available))
    gates.append(_run_readme(project_path))

    overall = "PASS" if all(g.status in ("PASS", "SKIP") for g in gates) else "FAIL"
    overall = "FAIL" if any(g.status == "FAIL" for g in gates) else overall
    return GatesResult(overall_status=overall, gates=gates)


# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------


async def _run_lint(project_path: Path) -> GateResult:
    """Gate 1: ruff. PASS si 0 erreurs."""
    started = time.perf_counter()
    if shutil.which("ruff") is None:
        return _skip(GATE_LINT, "ruff binary not in PATH", started)
    rc, stdout, stderr = await _exec(["ruff", "check", "--output-format=json", "."], project_path)
    if rc not in (0, 1):
        return _error(GATE_LINT, f"ruff rc={rc}: {stderr[-300:]}", started)
    try:
        findings = json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError:
        findings = []
    error_count = len(findings)
    score = 1.0 if error_count == 0 else max(0.0, 1.0 - error_count / 50)
    return GateResult(
        name=GATE_LINT,
        status="PASS" if error_count == 0 else "FAIL",
        score=round(score, 3),
        duration_ms=_elapsed_ms(started),
        details={"errors": error_count, "sample": findings[:5]},
    )


async def _run_pytest(project_path: Path, timeout_s: int) -> GateResult:
    """Gate 2: pytest. PASS si tous les tests passent."""
    started = time.perf_counter()
    if not (project_path / "tests").exists():
        return _fail(GATE_PYTEST, "tests/ directory missing", started)
    rc, stdout, stderr = await _exec(
        ["pytest", "-q", "--no-header", "--tb=short"], project_path, timeout=timeout_s,
    )
    parsed = _parse_pytest_summary(stdout)
    total = parsed["passed"] + parsed["failed"] + parsed["errors"]
    if total == 0:
        return _fail(GATE_PYTEST, f"no tests collected (rc={rc})", started, details=parsed)
    score = parsed["passed"] / total
    ok = parsed["failed"] == 0 and parsed["errors"] == 0 and rc == 0
    return GateResult(
        name=GATE_PYTEST,
        status="PASS" if ok else "FAIL",
        score=round(score, 3),
        duration_ms=_elapsed_ms(started),
        details={**parsed, "returncode": rc, "stderr_tail": stderr[-200:]},
    )


async def _run_coverage(project_path: Path, timeout_s: int) -> GateResult:
    """Gate 3: pytest --cov. PASS si coverage >= 70%."""
    started = time.perf_counter()
    if not _has_pytest_cov(project_path):
        return _skip(GATE_COVERAGE, "pytest-cov not in requirements", started)
    cov_json = project_path / ".coverage.json"
    cov_json.unlink(missing_ok=True)
    rc, stdout, stderr = await _exec(
        ["pytest", "--cov=app", "--cov-report=json", "--cov-report=term-missing:skip-covered",
         "-q", "--no-header"],
        project_path, timeout=timeout_s,
    )
    pct: float | None = None
    cov_file = project_path / "coverage.json"
    if cov_file.exists():
        try:
            data = json.loads(cov_file.read_text(encoding="utf-8"))
            pct = float(data.get("totals", {}).get("percent_covered", 0)) / 100.0
        except (json.JSONDecodeError, KeyError, ValueError):
            pct = None
    if pct is None:
        m = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)\s*%", stdout)
        pct = float(m.group(1)) / 100.0 if m else None
    if pct is None:
        return _fail(GATE_COVERAGE, f"coverage extraction failed (rc={rc})", started,
                     details={"stderr_tail": stderr[-200:]})
    if pct >= 0.90:
        score = 1.0
    elif pct >= COVERAGE_TARGET:
        score = 0.80
    elif pct >= COVERAGE_MIN:
        score = 0.60
    else:
        score = round(pct / COVERAGE_MIN * 0.50, 3)
    return GateResult(
        name=GATE_COVERAGE,
        status="PASS" if pct >= COVERAGE_MIN else "FAIL",
        score=score,
        duration_ms=_elapsed_ms(started),
        details={"percent_covered": round(pct, 4), "min": COVERAGE_MIN, "target": COVERAGE_TARGET},
    )


async def _run_docker_build(project_path: Path, docker_available: bool) -> GateResult:
    """Gate 4: docker build. SKIP si docker indisponible."""
    started = time.perf_counter()
    if not docker_available:
        return _skip(GATE_DOCKER_BUILD, "docker binary unavailable", started)
    if not (project_path / "Dockerfile").exists():
        return _fail(GATE_DOCKER_BUILD, "Dockerfile missing", started)
    image_tag = f"uba-gate-{project_path.name.lower()[:32]}:latest"
    rc, stdout, stderr = await _exec(
        ["docker", "build", "-t", image_tag, "."], project_path, timeout=600,
    )
    return GateResult(
        name=GATE_DOCKER_BUILD,
        status="PASS" if rc == 0 else "FAIL",
        score=1.0 if rc == 0 else 0.0,
        duration_ms=_elapsed_ms(started),
        details={"image_tag": image_tag, "returncode": rc, "stderr_tail": stderr[-300:]},
    )


async def _run_docker_run(project_path: Path, docker_available: bool) -> GateResult:
    """Gate 5: docker run + curl /health. SKIP si docker indisponible."""
    started = time.perf_counter()
    if not docker_available:
        return _skip(GATE_DOCKER_RUN, "docker binary unavailable", started)
    image_tag = f"uba-gate-{project_path.name.lower()[:32]}:latest"
    container_name = f"uba-gate-{project_path.name.lower()[:32]}"
    await _exec(["docker", "rm", "-f", container_name], project_path, timeout=10)
    rc, stdout, stderr = await _exec(
        ["docker", "run", "-d", "--rm", "--name", container_name,
         "-p", "8888:8000", image_tag],
        project_path, timeout=30,
    )
    if rc != 0:
        return _fail(GATE_DOCKER_RUN, f"docker run rc={rc}: {stderr[-200:]}", started)
    try:
        await asyncio.sleep(15)
        rc_curl, out_curl, err_curl = await _exec(
            ["curl", "-fsS", "-o", "-", "-w", "%{http_code}",
             "http://localhost:8888/health"],
            project_path, timeout=10,
        )
        http_code = out_curl[-3:] if len(out_curl) >= 3 else "000"
        ok = rc_curl == 0 and http_code == "200"
    finally:
        await _exec(["docker", "stop", container_name], project_path, timeout=15)
    return GateResult(
        name=GATE_DOCKER_RUN,
        status="PASS" if ok else "FAIL",
        score=1.0 if ok else 0.0,
        duration_ms=_elapsed_ms(started),
        details={"http_code": http_code if ok else None, "container": container_name},
    )


def _run_readme(project_path: Path) -> GateResult:
    """Gate 6: README sections obligatoires."""
    started = time.perf_counter()
    readme = project_path / "README.md"
    if not readme.exists():
        return _fail(GATE_README, "README.md missing", started)
    text = readme.read_text(encoding="utf-8", errors="replace").lower()
    present = [s for s in README_REQUIRED_SECTIONS if _has_section(text, s)]
    missing = [s for s in README_REQUIRED_SECTIONS if s not in present]
    has_curl = "curl " in text or "curl\n" in text
    has_env = ".env" in text or "environment" in text or "env vars" in text
    ratio = len(present) / len(README_REQUIRED_SECTIONS)
    bonus = (0.05 if has_curl else 0.0) + (0.05 if has_env else 0.0)
    score = min(1.0, ratio + bonus)
    ok = ratio == 1.0
    if ok:
        status = "PASS"
    elif ratio >= 0.5:
        status = "FAIL"
    else:
        status = "FAIL"
    return GateResult(
        name=GATE_README,
        status=status,
        score=round(score, 3),
        duration_ms=_elapsed_ms(started),
        details={"present": present, "missing": missing,
                 "has_curl_example": has_curl, "has_env_doc": has_env},
    )


# ---------------------------------------------------------------------------
# Persistence (delivery_quality_gates / quality_gate_failures)
# ---------------------------------------------------------------------------


async def persist_results(
    pool: Any,
    project_id: str,
    attempt_number: int,
    result: GatesResult,
) -> None:
    """Insert toutes les lignes de gates + failures pour un projet/attempt."""
    if pool is None:
        return
    async with pool.acquire() as conn:
        for gate in result.gates:
            await conn.execute(
                """
                INSERT INTO delivery_quality_gates
                  (project_id, attempt_number, gate_name, status, score,
                   duration_ms, details_json, checked_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW())
                """,
                project_id, attempt_number, gate.name, gate.status,
                gate.score, gate.duration_ms, json.dumps(gate.details),
            )
            if gate.status == "FAIL":
                await conn.execute(
                    """
                    INSERT INTO quality_gate_failures
                      (project_id, gate_name, attempt_number, error_msg)
                    VALUES ($1, $2, $3, $4)
                    """,
                    project_id, gate.name, attempt_number,
                    str(gate.details)[:1000],
                )


async def mark_failures_fixed(pool: Any, project_id: str, fixed_in_attempt: int) -> int:
    """Mark all open failures for a project as resolved by `fixed_in_attempt`."""
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        rec = await conn.execute(
            """
            UPDATE quality_gate_failures
               SET fixed_in_attempt = $2
             WHERE project_id = $1 AND fixed_in_attempt IS NULL
            """,
            project_id, fixed_in_attempt,
        )
    return _affected(rec)


def _affected(rec: str | None) -> int:
    if not rec:
        return 0
    parts = rec.split()
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_RE_PYTEST_NUM = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped)")


def _parse_pytest_summary(stdout: str) -> dict[str, int]:
    """Parse pytest summary lines in both verbose (`=== X passed in Y ===`)
    and quiet mode (`X passed in Y`)."""
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not stdout:
        return counts
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if " in " not in line:
            continue
        if not (line.startswith("=") or _RE_PYTEST_NUM.search(line)):
            continue
        for num, label in _RE_PYTEST_NUM.findall(line):
            label_norm = "errors" if label.startswith("error") else label
            counts[label_norm] = counts.get(label_norm, 0) + int(num)
        if any(counts.values()):
            break
    return counts


def _has_pytest_cov(project_path: Path) -> bool:
    req = project_path / "requirements.txt"
    if not req.exists():
        return False
    text = req.read_text(encoding="utf-8", errors="replace").lower()
    return "pytest-cov" in text


def _has_section(readme_lower: str, name: str) -> bool:
    pattern = re.compile(rf"(?m)^#{{1,3}}\s*{re.escape(name)}", re.IGNORECASE)
    if pattern.search(readme_lower):
        return True
    return f"## {name}" in readme_lower or f"# {name}" in readme_lower


def _docker_available() -> bool:
    return shutil.which("docker") is not None


async def _exec(cmd: list[str], cwd: Path, timeout: int = 60) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return -1, "", f"timeout after {timeout}s"
    return (
        proc.returncode or 0,
        (stdout_b or b"").decode("utf-8", errors="replace"),
        (stderr_b or b"").decode("utf-8", errors="replace"),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _skip(name: str, reason: str, started: float) -> GateResult:
    return GateResult(name=name, status="SKIP", score=0.0,
                      duration_ms=_elapsed_ms(started),
                      details={"reason": reason})


def _fail(name: str, reason: str, started: float, details: dict[str, Any] | None = None) -> GateResult:
    payload = {"reason": reason}
    if details:
        payload.update(details)
    return GateResult(name=name, status="FAIL", score=0.0,
                      duration_ms=_elapsed_ms(started), details=payload)


def _error(name: str, reason: str, started: float) -> GateResult:
    return GateResult(name=name, status="ERROR", score=0.0,
                      duration_ms=_elapsed_ms(started),
                      details={"reason": reason})
