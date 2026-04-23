"""Registre singleton des 23 agents (Ch.5.5 du CDC).

V2 : 10 agents prioritaires implementes reellement
  V1 : #01, #02, #04, #14, #21
  V2 : #03, #05, #06, #11, #18
Les autres restent des stubs structures en attendant la V3.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.bootstrap_agent import BootstrapAgent
from app.agents.claude_code_agent import ClaudeCodeAgent
from app.agents.conformite_dz_agent import ConformiteDzAgent
from app.agents.datadog_agent import DatadogAgent
from app.agents.docker_agent import DockerAgent
from app.agents.linter_agent import LinterAgent
from app.agents.pytest_agent import PytestAgent
from app.agents.readme_agent import ReadmeAgent
from app.agents.security_agent import SecurityAgent
from app.agents.sonarqube_agent import SonarQubeAgent
from app.agents.terraform_agent import TerraformAgent


class StubAgent(BaseAgent):
    """Stub : enregistre l'intention d'execution sans effet de bord."""

    def __init__(self, agent_id: str, name: str, category: str) -> None:
        super().__init__(agent_id=agent_id, name=name)
        self.category = category

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "category": self.category,
            "stub": True,
            "inputs_seen_keys": sorted(inputs.keys()),
        }


AGENT_CATALOG: list[tuple[str, str, str]] = [
    ("agent-00-bootstrap",     "Bootstrap Agent",        "meta"),
    ("agent-01-claude-code",   "Claude Code",            "development"),
    ("agent-02-sonarqube",     "SonarQube",              "testing"),
    ("agent-03-terraform",     "Terraform",              "infrastructure"),
    ("agent-04-pytest",        "Pytest Runner",          "testing"),
    ("agent-05-datadog",       "Datadog Monitor",        "monitoring"),
    ("agent-06-docker",        "Docker Builder",         "infrastructure"),
    ("agent-07-nginx",         "Nginx Config",           "infrastructure"),
    ("agent-08-github",        "GitHub Actions",         "infrastructure"),
    ("agent-09-swagger",       "Swagger/OpenAPI",        "documentation"),
    ("agent-10-db-migrator",   "DB Migrator",            "development"),
    ("agent-11-security",      "Security Scanner",       "security"),
    ("agent-12-load",          "Load Tester",            "testing"),
    ("agent-13-e2e",           "E2E Playwright",         "testing"),
    ("agent-14-linter",        "Code Linter",            "testing"),
    ("agent-15-formatter",     "Code Formatter",         "development"),
    ("agent-16-dep-checker",   "Dep Checker",            "security"),
    ("agent-17-backup",        "Backup Manager",         "infrastructure"),
    ("agent-18-conformite-dz", "Conformite DZ",          "compliance"),
    ("agent-19-i18n",          "I18n Agent",             "development"),
    ("agent-20-a11y",          "A11y Checker",           "testing"),
    ("agent-21-readme",        "README Gen",             "documentation"),
    ("agent-22-changelog",     "Changelog",              "documentation"),
    ("agent-23-notifier",      "Notifier",               "monitoring"),
]


REAL_AGENTS: dict[str, Callable[[], BaseAgent]] = {
    "agent-00-bootstrap":     BootstrapAgent,
    "agent-01-claude-code":   ClaudeCodeAgent,
    "agent-02-sonarqube":     SonarQubeAgent,
    "agent-03-terraform":     TerraformAgent,
    "agent-04-pytest":        PytestAgent,
    "agent-05-datadog":       DatadogAgent,
    "agent-06-docker":        DockerAgent,
    "agent-11-security":      SecurityAgent,
    "agent-14-linter":        LinterAgent,
    "agent-18-conformite-dz": ConformiteDzAgent,
    "agent-21-readme":        ReadmeAgent,
}


class AgentRegistry:
    _instance: AgentRegistry | None = None

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    @classmethod
    def get_instance(cls) -> AgentRegistry:
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_all()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    def _register_all(self) -> None:
        for agent_id, name, category in AGENT_CATALOG:
            if agent_id in REAL_AGENTS:
                agent = REAL_AGENTS[agent_id]()
                agent.category = category  # type: ignore[attr-defined]
                self._agents[agent_id] = agent
            else:
                self._agents[agent_id] = StubAgent(agent_id, name, category)

    def get(self, agent_id: str) -> BaseAgent:
        agent = self._agents.get(agent_id)
        if not agent:
            raise KeyError(f"Agent inconnu: {agent_id}")
        return agent

    def list_all(self) -> list[dict[str, Any]]:
        return [
            {
                "id": a.agent_id,
                "name": a.name,
                "version": a.version,
                "initialized": a._initialized,
                "category": getattr(a, "category", "unknown"),
                "implementation": "real" if a.agent_id in REAL_AGENTS else "stub",
            }
            for a in self._agents.values()
        ]

    async def initialize_all(self) -> None:
        await asyncio.gather(*[a.initialize() for a in self._agents.values()])
