"""Tests unitaires des 5 nouveaux agents V2 (deterministes, sans reseau)."""
from pathlib import Path

import pytest

from app.agents.conformite_dz_agent import ConformiteDzAgent
from app.agents.datadog_agent import DatadogAgent
from app.agents.docker_agent import DockerAgent
from app.agents.terraform_agent import TerraformAgent
from app.agents.workspace import Workspace


@pytest.mark.asyncio
async def test_terraform_agent_generates_valid_blocks(tmp_path: Path):
    ws = Workspace.create(task_id="tf-test", root=tmp_path)
    agent = TerraformAgent()
    result = await agent.execute({"workspace": ws, "spec": "paie dz"})
    assert result.status == "success"
    assert result.output["passed"] is True
    assert "terraform/main.tf" in result.output["files_written"]
    # Accolades equilibrees
    for rel in result.output["files_written"]:
        content = ws.read(rel)
        assert content.count("{") == content.count("}"), rel


@pytest.mark.asyncio
async def test_docker_agent_creates_compose_when_absent(tmp_path: Path):
    ws = Workspace.create(task_id="docker-test", root=tmp_path)
    # Workspace avec Dockerfile minimal sans bonnes pratiques
    ws.write("Dockerfile",
             "FROM python:3.12-slim\nCOPY . /app\nCMD [\"uvicorn\", \"app.main:app\"]\n")
    agent = DockerAgent()
    result = await agent.execute({"workspace": ws, "manifest": ws.manifest()})
    assert result.status == "success"
    out = result.output
    assert out["dockerfile_present"] is True
    assert "docker-compose.yml" in out["files_created"]
    assert out["checks"]["has_healthcheck"] is False
    assert out["checks"]["has_non_root_user"] is False
    assert out["score"] <= 0.80  # missing healthcheck + non-root


@pytest.mark.asyncio
async def test_docker_agent_rewards_best_practices(tmp_path: Path):
    ws = Workspace.create(task_id="docker-best", root=tmp_path)
    ws.write("Dockerfile", """FROM python:3.12-slim AS build
RUN useradd -r app
FROM python:3.12-slim
USER app
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app"]
""")
    agent = DockerAgent()
    result = await agent.execute({"workspace": ws, "manifest": ws.manifest()})
    assert result.output["score"] >= 0.90


@pytest.mark.asyncio
async def test_conformite_dz_detects_paie_domain(tmp_path: Path):
    ws = Workspace.create(task_id="dz-paie", root=tmp_path)
    ws.write("app/business.py", """
# TVA 19% et TAP 2%
CNAS_SAL = 0.09
CNAS_EMP = 0.26
def irg(brut):
    # Bareme progressif IRG 2024 : 30000 / 120000 / 360000 / 1440000
    return 0
def valider_nin(nin: str) -> bool:
    return len(nin) == 18
# Montants en DZD (Dinar algerien)
""")
    ws.write("README.md", "Module Paie DZ : TVA 19%, TAP 2%, CNAS 9%/26%. Devise DZD.\n")
    agent = ConformiteDzAgent()
    result = await agent.execute({
        "workspace": ws, "spec": "Module paie RH CNAS IRG",
        "manifest": ws.manifest(),
    })
    rules = {r["rule"]: r for r in result.output["rules"]}
    assert rules["R1_TVA19"]["passed"] is True
    assert rules["R2_TAP2"]["passed"] is True
    assert rules["R3_CNAS"]["applicable"] is True and rules["R3_CNAS"]["passed"] is True
    assert rules["R6_DZD"]["passed"] is True
    assert result.output["score"] >= 0.85


@pytest.mark.asyncio
async def test_conformite_dz_flags_foreign_regs(tmp_path: Path):
    ws = Workspace.create(task_id="dz-flag", root=tmp_path)
    ws.write("README.md", "Compliant with HIPAA and SOX standards. DZD used.\n")
    agent = ConformiteDzAgent()
    result = await agent.execute({
        "workspace": ws, "spec": "client API", "manifest": ws.manifest(),
    })
    r7 = next(r for r in result.output["rules"] if r["rule"] == "R7_NoForeignRegs")
    assert r7["passed"] is False
    assert "HIPAA" in r7["evidence"] or "SOX" in r7["evidence"]


@pytest.mark.asyncio
async def test_datadog_extracts_endpoints(tmp_path: Path):
    ws = Workspace.create(task_id="dd-test", root=tmp_path)
    ws.write("app/main.py", '''
from fastapi import FastAPI
app = FastAPI()
@app.get("/health")
def h(): return {}
@app.post("/clients")
def c(): return {}
''')
    agent = DatadogAgent()
    result = await agent.execute({
        "workspace": ws, "spec": "paie dz", "manifest": ws.manifest(),
    })
    assert result.output["passed"] is True
    assert "/health" in result.output["endpoints_monitored"]
    assert "/clients" in result.output["endpoints_monitored"]
    assert "monitoring/dashboard.json" in result.output["files_written"]
