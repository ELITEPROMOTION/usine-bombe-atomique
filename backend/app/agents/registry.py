"""Registre singleton des 23 agents (Ch.5.5 du CDC).

En V0 bootstrap les agents sont des stubs: chaque classe retourne
un output vide mais correct structurellement. Les implementations
metier sont remplies par l'orchestrateur dans les iterations suivantes.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.agents.base_agent import BaseAgent


class _StubAgent(BaseAgent):
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


# Registre figé conforme CDC Ch.5.5. L'ordre est canonique.
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


class AgentRegistry:
    _instance: "AgentRegistry | None" = None

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._register_all()
        return cls._instance

    def _register_all(self) -> None:
        for agent_id, name, category in AGENT_CATALOG:
            self._agents[agent_id] = _StubAgent(agent_id, name, category)

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
            }
            for a in self._agents.values()
        ]

    async def initialize_all(self) -> None:
        await asyncio.gather(*[a.initialize() for a in self._agents.values()])
