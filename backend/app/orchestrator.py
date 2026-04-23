"""Orchestrateur DAG parallele (CDC Ch.4.3).

Principe :
- Chaque tache est decrite comme un DAG de noeuds `agent_id` + dependances.
- Une vague = tous les noeuds dont les dependances sont resolues.
- Les noeuds d'une vague s'executent en parallele via `asyncio.gather`.
- Les outputs de chaque noeud sont injectes dans le contexte partage, et
  les noeuds aval peuvent les recuperer via `inputs_from`.

Le DAG par defaut (V1 CRUD) :

    01 Claude Code (genere le code)
         |
    +----+----+---------------+
    v         v               v
    14 Lint   02 SonarQube    04 Pytest
                                  |
                                  v
                             21 README

Lint / SonarQube / Pytest sont independants une fois que le code existe :
ils tournent en parallele dans la meme vague. README est genere a la fin
pour refleter le manifest final.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base_agent import AgentResult
from app.agents.registry import AgentRegistry
from app.agents.workspace import Workspace

logger = logging.getLogger(__name__)


@dataclass
class DagNode:
    agent_id: str
    depends_on: list[str] = field(default_factory=list)
    inputs_from: list[str] = field(default_factory=list)


@dataclass
class OrchestrationResult:
    task_id: str
    workspace: Workspace
    results: dict[str, AgentResult]
    waves: list[list[str]]
    duration_ms: float
    status: str  # success | partial | failed
    priority: str = "high"


def default_dag() -> list[DagNode]:
    """DAG V2 : 10 agents reels en 3 vagues paralleles.

    Vague 1 : generation (Tri-Cerveau Builder/Critic/Judge).
    Vague 2 : analyse + infra paralleles (lint, sonar, pytest, terraform, docker, dz).
    Vague 3 : securite + monitoring + readme (lisent le manifest final).
    """
    return [
        # Wave 1
        DagNode(agent_id="agent-01-claude-code"),
        # Wave 2 : tous dependent uniquement de la generation
        DagNode(agent_id="agent-14-linter",       depends_on=["agent-01-claude-code"]),
        DagNode(agent_id="agent-02-sonarqube",    depends_on=["agent-01-claude-code"]),
        DagNode(agent_id="agent-04-pytest",       depends_on=["agent-01-claude-code"]),
        DagNode(agent_id="agent-03-terraform",    depends_on=["agent-01-claude-code"]),
        DagNode(agent_id="agent-06-docker",       depends_on=["agent-01-claude-code"],
                inputs_from=["agent-01-claude-code"]),
        DagNode(agent_id="agent-18-conformite-dz", depends_on=["agent-01-claude-code"],
                inputs_from=["agent-01-claude-code"]),
        # Wave 3 : utilisent le manifest final (avec infra et Dockerfile ajustes)
        DagNode(agent_id="agent-11-security",
                depends_on=["agent-02-sonarqube", "agent-03-terraform", "agent-06-docker"]),
        DagNode(agent_id="agent-05-datadog",
                depends_on=["agent-03-terraform", "agent-06-docker"],
                inputs_from=["agent-01-claude-code"]),
        DagNode(agent_id="agent-21-readme",
                depends_on=["agent-03-terraform", "agent-06-docker", "agent-11-security",
                            "agent-05-datadog", "agent-18-conformite-dz"],
                inputs_from=["agent-01-claude-code"]),
    ]


def topological_waves(dag: list[DagNode]) -> list[list[str]]:
    """Regroupe les noeuds en vagues parallelisables (Kahn)."""
    pending = {n.agent_id: set(n.depends_on) for n in dag}
    order: list[list[str]] = []
    while pending:
        ready = sorted(aid for aid, deps in pending.items() if not deps)
        if not ready:
            raise ValueError(f"DAG cycle detected among: {sorted(pending.keys())}")
        order.append(ready)
        for aid in ready:
            pending.pop(aid)
        for deps in pending.values():
            deps.difference_update(ready)
    return order


async def run_dag(
    task_id: str,
    spec: str,
    dag: list[DagNode] | None = None,
    workspace: Workspace | None = None,
    priority: str = "high",
) -> OrchestrationResult:
    dag = dag or default_dag()
    workspace = workspace or Workspace.create(task_id)
    registry = AgentRegistry.get_instance()
    await registry.initialize_all()

    node_by_id = {n.agent_id: n for n in dag}
    waves = topological_waves(dag)
    results: dict[str, AgentResult] = {}
    start = time.perf_counter()

    for wave in waves:
        coros = [
            _run_node(registry, node_by_id[aid], spec, workspace, results, priority)
            for aid in wave
        ]
        wave_results = await asyncio.gather(*coros, return_exceptions=False)
        for aid, res in zip(wave, wave_results, strict=False):
            results[aid] = res
        if any(r.status == "failed" for r in wave_results if r.agent_id.startswith("agent-01")):
            break  # si la generation echoue, inutile de continuer

    duration_ms = (time.perf_counter() - start) * 1000
    failed = [r for r in results.values() if r.status == "failed"]
    status = "success" if not failed else ("partial" if len(failed) < len(results) else "failed")

    return OrchestrationResult(
        task_id=task_id,
        workspace=workspace,
        results=results,
        waves=waves,
        duration_ms=duration_ms,
        status=status,
        priority=priority,
    )


async def _run_node(
    registry: AgentRegistry,
    node: DagNode,
    spec: str,
    workspace: Workspace,
    prior: dict[str, AgentResult],
    priority: str = "high",
) -> AgentResult:
    agent = registry.get(node.agent_id)
    inputs: dict[str, Any] = {
        "task_id": workspace.task_id,
        "spec": spec,
        "workspace": workspace,
        "priority": priority,
    }
    for upstream_id in node.inputs_from:
        up = prior.get(upstream_id)
        if up and up.output:
            for key in ("manifest", "files", "source"):
                if key in up.output:
                    inputs[key] = up.output[key]
    logger.info("DAG run node=%s", node.agent_id)
    return await agent.execute(inputs)
