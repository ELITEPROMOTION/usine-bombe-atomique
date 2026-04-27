"""V8.5 — Tests unitaires des 6 quality gates et du score breakdown."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.orchestration import quality_gates as qg
from app.orchestration.validation_score_v2 import (
    ACCEPTED_MIN,
    MAX_TOTAL,
    PARTIAL_MIN,
    compute_breakdown,
    decision_for,
)


# ---------------------------------------------------------------------------
# pytest summary parser (helper reutilise par PytestGate)
# ---------------------------------------------------------------------------


def test_parse_pytest_summary_passes_only() -> None:
    out = "test_a.py .....                                            [100%]\n" \
          "============= 5 passed in 0.12s ============="
    counts = qg._parse_pytest_summary(out)
    assert counts == {"passed": 5, "failed": 0, "errors": 0, "skipped": 0}


def test_parse_pytest_summary_quiet_mode_no_brackets() -> None:
    """pytest -q produces a summary line without === brackets."""
    out = "..............................................                           [100%]\n" \
          "46 passed in 1.20s"
    counts = qg._parse_pytest_summary(out)
    assert counts["passed"] == 46
    assert counts["failed"] == 0


def test_parse_pytest_summary_mixed() -> None:
    out = "============ 3 passed, 2 failed, 1 error in 0.34s ============"
    counts = qg._parse_pytest_summary(out)
    assert counts["passed"] == 3
    assert counts["failed"] == 2
    assert counts["errors"] == 1


def test_parse_pytest_summary_no_tests() -> None:
    counts = qg._parse_pytest_summary("=== no tests ran in 0.01s ===")
    assert counts == {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def test_parse_pytest_summary_empty() -> None:
    assert qg._parse_pytest_summary("") == {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


# ---------------------------------------------------------------------------
# README gate (pure file IO, no subprocess)
# ---------------------------------------------------------------------------


def _make_readme(path: Path, sections: list[str], extras: str = "") -> None:
    body = "\n\n".join(f"## {s.title()}" for s in sections)
    path.write_text(body + "\n\n" + extras, encoding="utf-8")


def test_readme_gate_all_sections(tmp_path: Path) -> None:
    _make_readme(tmp_path / "README.md", list(qg.README_REQUIRED_SECTIONS),
                 extras="```bash\ncurl http://x/health\n```\n.env example\n")
    g = qg._run_readme(tmp_path)
    assert g.status == "PASS"
    assert g.score == 1.0
    assert set(g.details["present"]) == set(qg.README_REQUIRED_SECTIONS)
    assert g.details["missing"] == []
    assert g.details["has_curl_example"] is True


def test_readme_gate_missing_some(tmp_path: Path) -> None:
    _make_readme(tmp_path / "README.md", ["description", "installation", "usage"])
    g = qg._run_readme(tmp_path)
    assert g.status == "FAIL"
    assert "tests" in g.details["missing"]
    assert "deploy" in g.details["missing"]


def test_readme_gate_missing_file(tmp_path: Path) -> None:
    g = qg._run_readme(tmp_path)
    assert g.status == "FAIL"
    assert g.details["reason"] == "README.md missing"


# ---------------------------------------------------------------------------
# Lint gate — fake ruff via PATH manipulation
# ---------------------------------------------------------------------------


def test_lint_gate_skips_when_ruff_absent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("shutil.which", lambda _: None)
    res = asyncio.run(qg._run_lint(tmp_path))
    assert res.status == "SKIP"


# ---------------------------------------------------------------------------
# Coverage gate — pytest-cov detection
# ---------------------------------------------------------------------------


def test_has_pytest_cov_detects_in_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\npytest-cov>=5.0\n", encoding="utf-8")
    assert qg._has_pytest_cov(tmp_path) is True


def test_has_pytest_cov_absent_when_not_in_requirements(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("fastapi\npytest>=8\n", encoding="utf-8")
    assert qg._has_pytest_cov(tmp_path) is False


def test_has_pytest_cov_no_requirements_file(tmp_path: Path) -> None:
    assert qg._has_pytest_cov(tmp_path) is False


def test_coverage_gate_skips_when_no_pytest_cov(tmp_path: Path) -> None:
    res = asyncio.run(qg._run_coverage(tmp_path, timeout_s=5))
    assert res.status == "SKIP"


# ---------------------------------------------------------------------------
# GatesResult aggregation
# ---------------------------------------------------------------------------


def _gate(name: str, status: str, score: float = 0.0, details: dict | None = None) -> qg.GateResult:
    return qg.GateResult(name=name, status=status, score=score, duration_ms=10,
                         details=details or {})


def test_gates_result_summary_counters() -> None:
    res = qg.GatesResult(
        overall_status="FAIL",
        gates=[
            _gate("a", "PASS"),
            _gate("b", "PASS"),
            _gate("c", "FAIL"),
            _gate("d", "SKIP"),
        ],
    )
    assert res.passed_count == 2
    assert res.failed_count == 1
    assert res.skipped_count == 1
    assert "2/4 PASS" in res.summary
    assert res.first_failure().name == "c"


# ---------------------------------------------------------------------------
# ScoreBreakdown — every component scenario
# ---------------------------------------------------------------------------


def _full_pass_gates(*, docker_skipped: bool = False) -> qg.GatesResult:
    docker_status = "SKIP" if docker_skipped else "PASS"
    docker_score = 0.0 if docker_skipped else 1.0
    gates = [
        _gate(qg.GATE_LINT, "PASS", 1.0, {"errors": 0}),
        _gate(qg.GATE_PYTEST, "PASS", 1.0, {"passed": 46, "failed": 0, "errors": 0}),
        _gate(qg.GATE_COVERAGE, "PASS", 1.0, {"percent_covered": 0.95}),
        _gate(qg.GATE_DOCKER_BUILD, docker_status, docker_score, {}),
        _gate(qg.GATE_DOCKER_RUN, docker_status, docker_score, {"http_code": "200" if not docker_skipped else None}),
        _gate(qg.GATE_README, "PASS", 1.0, {
            "present": list(qg.README_REQUIRED_SECTIONS),
            "missing": [],
            "has_curl_example": True,
            "has_env_doc": True,
        }),
    ]
    return qg.GatesResult(overall_status="PASS", gates=gates)


def test_breakdown_all_pass_with_docker() -> None:
    bd = compute_breakdown(_full_pass_gates(docker_skipped=False))
    assert bd.total == 100
    assert bd.decision == "ACCEPTED"
    assert bd.pytest_pass == 30
    assert bd.docker_build == 20
    assert bd.coverage == 15
    assert bd.lint_clean == 15
    assert bd.smoke_test == 10
    assert bd.readme == 10


def test_breakdown_docker_skipped_normalizes_decision() -> None:
    bd = compute_breakdown(_full_pass_gates(docker_skipped=True))
    # 100 - 20 (docker) - 10 (smoke) = 70 max
    assert bd.total == 70
    assert bd.decision == "ACCEPTED"  # accepted_min reduit a 50


def test_breakdown_pytest_fail_drops_30_points() -> None:
    gates = _full_pass_gates(docker_skipped=False).gates
    gates[1] = _gate(qg.GATE_PYTEST, "FAIL", 0.0, {"reason": "1 test failed"})
    bd = compute_breakdown(qg.GatesResult(overall_status="FAIL", gates=gates))
    assert bd.pytest_pass == 0
    assert bd.total == 70
    assert bd.decision == "PARTIAL"


def test_breakdown_coverage_tiers() -> None:
    for pct, expected in [(0.95, 15), (0.85, 12), (0.72, 9), (0.50, 0)]:
        gates = _full_pass_gates(docker_skipped=False).gates
        gates[2] = _gate(qg.GATE_COVERAGE, "PASS" if pct >= 0.70 else "FAIL", 0.5,
                         {"percent_covered": pct})
        bd = compute_breakdown(qg.GatesResult(overall_status="PASS", gates=gates))
        assert bd.coverage == expected, f"pct={pct}"


def test_breakdown_lint_tiers() -> None:
    cases = [(0, 15), (3, 10), (10, 5), (50, 0)]
    for errors, expected in cases:
        gates = _full_pass_gates(docker_skipped=False).gates
        gates[0] = _gate(qg.GATE_LINT, "PASS" if errors == 0 else "FAIL", 0.5,
                         {"errors": errors})
        bd = compute_breakdown(qg.GatesResult(overall_status="PASS", gates=gates))
        assert bd.lint_clean == expected, f"errors={errors}"


def test_breakdown_readme_partial() -> None:
    gates = _full_pass_gates(docker_skipped=False).gates
    gates[5] = _gate(qg.GATE_README, "FAIL", 0.5, {
        "present": ["description", "installation", "usage", "tests"],
        "missing": ["deploy", "license"],
        "has_curl_example": False,
        "has_env_doc": False,
    })
    bd = compute_breakdown(qg.GatesResult(overall_status="FAIL", gates=gates))
    assert bd.readme == 5  # 4/6 = 0.66 -> 5 pts


def test_breakdown_total_zero_yields_rejected() -> None:
    empty_gate = lambda name: _gate(name, "FAIL", 0.0, {})
    res = qg.GatesResult(
        overall_status="FAIL",
        gates=[empty_gate(name) for name in (
            qg.GATE_LINT, qg.GATE_PYTEST, qg.GATE_COVERAGE,
            qg.GATE_DOCKER_BUILD, qg.GATE_DOCKER_RUN, qg.GATE_README,
        )],
    )
    bd = compute_breakdown(res)
    assert bd.total == 0
    assert bd.decision == "REJECTED"


def test_breakdown_to_dict_shape() -> None:
    bd = compute_breakdown(_full_pass_gates(docker_skipped=False))
    d = bd.to_dict()
    assert d["scale"] == MAX_TOTAL
    assert d["decision"] == "ACCEPTED"
    assert d["total"] == 100
    assert set(d["components"]) == {
        "pytest_pass", "docker_build", "coverage", "lint_clean", "readme", "smoke_test",
    }
    assert d["thresholds"]["accepted"] == ACCEPTED_MIN
    assert d["thresholds"]["partial"] == PARTIAL_MIN


# ---------------------------------------------------------------------------
# decision_for utility
# ---------------------------------------------------------------------------


def test_decision_for_thresholds() -> None:
    assert decision_for(80) == "ACCEPTED"
    assert decision_for(79) == "PARTIAL"
    assert decision_for(60) == "PARTIAL"
    assert decision_for(59) == "REJECTED"
    assert decision_for(0) == "REJECTED"


def test_decision_for_docker_skipped_lowers_floor() -> None:
    # docker+smoke = 30 pts retires => accepted_min = 50
    assert decision_for(50, docker_skipped=True) == "ACCEPTED"
    assert decision_for(49, docker_skipped=True) == "PARTIAL"
    assert decision_for(29, docker_skipped=True) == "REJECTED"


# ---------------------------------------------------------------------------
# Integration-light : run gates on a tiny fake project (no docker/ruff/pytest-cov)
# ---------------------------------------------------------------------------


def test_validate_deliverable_minimal_project(tmp_path: Path, monkeypatch) -> None:
    # Simule l'absence de tous les binaires externes => SKIP partout sauf README + pytest
    # On force docker indispo via parameter et ruff/pytest-cov absents naturellement
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_smoke.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("pytest>=8.0\n", encoding="utf-8")
    _make_readme(tmp_path / "README.md", list(qg.README_REQUIRED_SECTIONS),
                 extras="```bash\ncurl /health\n```\n")
    monkeypatch.setattr("shutil.which", lambda name: "/fake/pytest" if name == "pytest" else None)

    async def runner():
        return await qg.validate_deliverable(tmp_path, docker_available=False, pytest_timeout_s=15)

    # Le ruff lookup retourne None -> skip, pytest binary present (mais on ne va pas l'invoquer
    # ici car on stub _exec)
    out = asyncio.run(runner())
    assert out.overall_status in ("PASS", "FAIL")
    names = [g.name for g in out.gates]
    assert names == list(qg.GATE_ORDER)
    docker_gates = [g for g in out.gates if g.name in (qg.GATE_DOCKER_BUILD, qg.GATE_DOCKER_RUN)]
    assert all(g.status == "SKIP" for g in docker_gates)


# ---------------------------------------------------------------------------
# pytest_agent fallback parser
# ---------------------------------------------------------------------------


def test_pytest_agent_parser_pure_passed() -> None:
    from app.agents.pytest_agent import _parse_pytest_stdout
    counts = _parse_pytest_stdout("======== 12 passed in 0.5s ========")
    assert counts == {"passed": 12, "failed": 0, "errors": 0, "total": 12}


def test_pytest_agent_parser_quiet_mode() -> None:
    """Same parser must accept `46 passed in 1.20s` without brackets."""
    from app.agents.pytest_agent import _parse_pytest_stdout
    out = "..............................................                           [100%]\n46 passed in 1.20s"
    counts = _parse_pytest_stdout(out)
    assert counts["passed"] == 46
    assert counts["total"] == 46


def test_pytest_agent_parser_mixed() -> None:
    from app.agents.pytest_agent import _parse_pytest_stdout
    counts = _parse_pytest_stdout("======== 3 failed, 7 passed, 1 error in 1.2s ========")
    assert counts["passed"] == 7
    assert counts["failed"] == 3
    assert counts["errors"] == 1
    assert counts["total"] == 11


def test_pytest_agent_parser_no_tests() -> None:
    from app.agents.pytest_agent import _parse_pytest_stdout
    counts = _parse_pytest_stdout("======== no tests ran in 0.01s ========")
    assert counts == {"passed": 0, "failed": 0, "errors": 0, "total": 0}


def test_pytest_agent_unrecognized_args_detection() -> None:
    from app.agents.pytest_agent import _is_unrecognized_args
    stderr = "ERROR: usage: ... error: unrecognized arguments: --json-report"
    assert _is_unrecognized_args(4, stderr) is True
    assert _is_unrecognized_args(2, stderr) is True
    assert _is_unrecognized_args(0, stderr) is False
    assert _is_unrecognized_args(4, "some other error") is False
