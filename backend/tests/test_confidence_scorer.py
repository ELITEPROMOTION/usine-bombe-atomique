"""Tests du confidence_scorer 6 dimensions."""
import pytest

from app.agents.base_agent import AgentResult
from app.orchestration.confidence_scorer import WEIGHTS, score_confidence


def test_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0, rel=1e-9)
    assert set(WEIGHTS.keys()) == {
        "correctness", "quality", "coverage", "security", "conformity", "maintainability"
    }


def _res(agent_id: str, score: float | None = None, **extra) -> AgentResult:
    output = {"score": score} if score is not None else {}
    output.update(extra)
    return AgentResult(agent_id=agent_id, agent_name=agent_id, status="success", output=output)


def test_perfect_project_scores_very_high():
    manifest = [
        {"path": "app/main.py",      "type": "source_code", "language": "python", "size_bytes": 900},
        {"path": "app/models.py",    "type": "source_code", "language": "python", "size_bytes": 900},
        {"path": "tests/test_a.py",  "type": "test",        "language": "python", "size_bytes": 900},
        {"path": "tests/test_b.py",  "type": "test",        "language": "python", "size_bytes": 900},
        {"path": "README.md",        "type": "documentation", "language": "markdown", "size_bytes": 1200},
    ]
    agents = {
        "agent-04-pytest":    _res("agent-04-pytest",    score=1.0),
        "agent-14-linter":    _res("agent-14-linter",    score=1.0),
        "agent-02-sonarqube": _res("agent-02-sonarqube", score=1.0,
                                   complexity={"average_complexity": 2.5}),
        "agent-11-security":  _res("agent-11-security",  score=1.0),
        "agent-18-conformite-dz": _res("agent-18-conformite-dz", score=1.0),
    }
    levels = [{"level": 2, "score": 1.0, "passed": True}]
    report = score_confidence(manifest, agents, levels)
    assert report.composite >= 0.95
    assert report.label == "very_high"
    assert {d.name for d in report.dimensions} == set(WEIGHTS.keys())


def test_empty_project_scores_very_low():
    report = score_confidence([], {}, [])
    assert report.composite < 0.3
    assert report.label in ("very_low", "low")


def test_security_fallback_to_sonar_when_agent11_absent():
    manifest = [{"path": "app/main.py", "type": "source_code", "language": "python", "size_bytes": 100}]
    agents = {"agent-02-sonarqube": _res("agent-02-sonarqube", score=0.6,
                                         complexity={"average_complexity": 3})}
    report = score_confidence(manifest, agents, [])
    sec = next(d for d in report.dimensions if d.name == "security")
    assert sec.score == pytest.approx(0.6, abs=1e-6)
