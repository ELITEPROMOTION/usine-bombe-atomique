"""Tests Tri-Cerveau : Builder/Critic/Judge verdicts + refinement loop."""
from pathlib import Path

import pytest

from app.agents.workspace import Workspace
from app.orchestration.tri_brain import (
    CriticIssue,
    _deterministic_critic,
    _judge,
    run_tri_brain,
)


def test_judge_reject_on_critical():
    decision = _judge([CriticIssue("critical", "syntax", "boom", "x.py")])
    assert decision.verdict == "reject"
    assert decision.critical_count == 1


def test_judge_refine_on_3_majors():
    issues = [CriticIssue("major", "quality", f"m{i}", None) for i in range(3)]
    decision = _judge(issues)
    assert decision.verdict == "refine"
    assert decision.major_count == 3


def test_judge_approve_on_clean():
    assert _judge([]).verdict == "approve"
    assert _judge([CriticIssue("minor", "quality", "m", None)]).verdict == "approve"


def test_deterministic_critic_detects_missing_tests():
    files = {"main.py": "print('x')\n", "requirements.txt": "fastapi==0.115.0\n"}
    issues = _deterministic_critic(files)
    assert any("test" in i.message.lower() for i in issues)


def test_deterministic_critic_detects_syntax_error():
    files = {"app/main.py": "def broken(\n", "requirements.txt": "x\n",
             "tests/test_x.py": "def test_ok(): pass\n"}
    issues = _deterministic_critic(files)
    assert any(i.severity == "critical" and i.category == "syntax" for i in issues)


@pytest.mark.asyncio
async def test_run_tri_brain_approves_good_build(tmp_path: Path):
    async def builder(_spec, _prior):
        return {
            "app/__init__.py": '"""pkg."""\n',
            "app/main.py": '"""ok."""\nfrom fastapi import FastAPI\napp = FastAPI()\n'
                           '@app.get("/", response_model=dict)\ndef r() -> dict: return {}\n',
            "requirements.txt": "fastapi==0.115.0\n",
            "tests/__init__.py": "",
            "tests/test_x.py": "def test_ok():\n    assert 1 == 1\n",
        }
    ws = Workspace.create(task_id="tb-good", root=tmp_path)
    report = await run_tri_brain("spec", ws, builder=builder, max_rounds=1)
    assert report.final_verdict == "approve"
    assert report.rounds == 0


@pytest.mark.asyncio
async def test_run_tri_brain_refines_then_approves(tmp_path: Path):
    """Premier build : 3 majors (pas de tests, pas de requirements, endpoint sans response_model)
    mais aucun critical -> refine. Refinement livre un projet propre -> approve."""
    calls: list[int] = []

    async def builder(_spec, prior):
        calls.append(1)
        if prior is None:
            return {
                "app/main.py": (
                    '"""bad."""\n'
                    "from fastapi import FastAPI\n"
                    "app = FastAPI()\n"
                    "@app.get('/a')\n"
                    "def a(): return {}\n"
                    "@app.get('/b')\n"
                    "def b(): return {}\n"
                ),
            }
        return {
            "app/__init__.py": '"""pkg."""\n',
            "app/main.py": (
                '"""ok."""\n'
                "from fastapi import FastAPI\n"
                "app = FastAPI()\n"
                "@app.get('/a', response_model=dict)\n"
                "def a() -> dict:\n    return {}\n"
            ),
            "requirements.txt": "fastapi==0.115.0\n",
            "tests/__init__.py": "",
            "tests/test_x.py": "def test_ok():\n    assert 1\n",
        }

    ws = Workspace.create(task_id="tb-refine", root=tmp_path)
    report = await run_tri_brain("spec", ws, builder=builder, max_rounds=1)
    assert len(calls) == 2, f"expected 2 builder calls, got {len(calls)}"
    assert report.rounds == 1
    assert report.final_verdict == "approve"
    # Le 1er verdict doit etre 'refine' (3 majors, 0 critical)
    assert report.judge_history[0].verdict == "refine"
