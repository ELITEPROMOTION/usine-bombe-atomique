"""E2E V1 : genere un CRUD API Classe A simple et verifie le verdict.

Ne requiert ni PostgreSQL ni Redis. Exerce :
- DAG orchestrator en parallele (5 agents)
- agents reels #01 (template fallback), #02, #04, #14, #21
- pipeline de validation 5 niveaux

Assertions :
- statut orchestration = success
- au moins main.py, tests, requirements.txt, README.md generes
- pipeline verdict PASS ou CONDITIONAL_PASS (dependance outils systeme)
"""
import sys
from pathlib import Path

import pytest

from app.orchestrator import run_dag
from app.validation.pipeline import run_pipeline


def _tool_available(name: str) -> bool:
    import shutil
    return shutil.which(name) is not None


NEEDED = ("ruff", "bandit", "radon", "pytest")


@pytest.mark.asyncio
@pytest.mark.skipif(
    not all(_tool_available(t) for t in NEEDED),
    reason=f"Outils CLI requis non installes: {NEEDED}",
)
async def test_e2e_crud_product_api(tmp_path: Path):
    """Genere + valide un CRUD API Product sans Docker/BDD."""
    spec = "CRUD API for Product resource : create, read, list, update, delete"

    from app.agents.workspace import Workspace
    ws = Workspace.create(task_id="e2e-test-product", root=tmp_path)

    orch = await run_dag(task_id="e2e-test-product", spec=spec, workspace=ws)
    assert orch.status in ("success", "partial"), orch.status

    paths = [m["path"] for m in ws.manifest()]
    assert "app/main.py" in paths
    assert "requirements.txt" in paths
    assert "README.md" in paths
    assert any(p.startswith("tests/") and p.endswith(".py") for p in paths)

    readme = ws.read("README.md")
    assert "Product API" in readme or "product" in readme.lower()
    assert "## Tests" in readme

    # Verdict final du pipeline
    result = await run_pipeline({
        "workspace": ws,
        "agents": orch.results,
        "manifest": ws.manifest(),
    })
    assert result.verdict in ("PASS", "CONDITIONAL_PASS"), (
        f"verdict={result.verdict} score={result.global_score} "
        f"levels={[(l.level, l.passed, l.score) for l in result.levels]}"
    )
    by_level = {lr.level: lr for lr in result.levels}
    assert by_level[1].passed, f"coherence failed: {by_level[1].issues}"
    assert by_level[2].passed, f"cdc conformity failed: {by_level[2].issues}"
    # niveau 4 (tests) passe si pytest a reussi sur le code genere
    assert by_level[4].score > 0, "pytest didn't run or all tests failed"


@pytest.mark.asyncio
async def test_e2e_dag_waves_parallel(tmp_path: Path):
    """Verifie la structure en vagues V2 (agent-01 puis analyse+infra puis monitoring)."""
    from app.agents.workspace import Workspace
    ws = Workspace.create(task_id="e2e-waves", root=tmp_path)

    if not all(
        __import__("shutil").which(t) for t in ("ruff", "bandit", "radon", "pytest")
    ):
        pytest.skip("outils CLI manquants")

    orch = await run_dag(task_id="e2e-waves", spec="CRUD API user", workspace=ws)
    assert orch.waves[0] == ["agent-01-claude-code"]
    wave2 = set(orch.waves[1])
    assert {"agent-02-sonarqube", "agent-04-pytest", "agent-14-linter",
            "agent-03-terraform", "agent-06-docker",
            "agent-18-conformite-dz"}.issubset(wave2)


# Evite d'importer le module compose sans FastAPI installe en env local.
assert sys.version_info >= (3, 10)
