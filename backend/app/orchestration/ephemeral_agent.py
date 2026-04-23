"""Ephemeral Agent Factory V4.1 - agents generes a la volee pour des problemes
non couverts par le catalogue.

**Securite** : aucune execution de code arbitraire. La factory genere un
agent a partir d'un *modele* predefini (whitelist) parmi :
- `regex_scanner`    : applique un pattern regex et renvoie les matches
- `file_counter`     : compte les fichiers d'un type (*.py, *.md, ...)
- `content_grepper`  : trouve des lignes contenant un mot cle
- `json_extractor`   : extrait un chemin JSON donne d'un artefact

L'agent est enregistre temporairement dans le registre, execute une
seule fois, puis desenregistre. Une entree est memorisee dans
`evidence_ledger` (kind=decision) + `improvement_backlog` si le probleme
est recurrent.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


ALLOWED_TEMPLATES = frozenset({
    "regex_scanner", "file_counter", "content_grepper", "json_extractor",
})


@dataclass
class EphemeralSpec:
    template: str
    params: dict[str, Any] = field(default_factory=dict)
    ttl_runs: int = 1


class EphemeralAgent(BaseAgent):
    """Agent temporaire, charge d'une mission tres etroite."""

    def __init__(self, agent_id: str, spec: EphemeralSpec) -> None:
        super().__init__(agent_id=agent_id, name=f"Ephemeral {spec.template}")
        self.spec = spec
        self.category = "ephemeral"
        self._runs_left = spec.ttl_runs

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self._runs_left -= 1
        tmpl = self.spec.template
        if tmpl == "regex_scanner":
            return _run_regex(inputs, self.spec.params)
        if tmpl == "file_counter":
            return _run_file_counter(inputs, self.spec.params)
        if tmpl == "content_grepper":
            return _run_grepper(inputs, self.spec.params)
        if tmpl == "json_extractor":
            return _run_json_extract(inputs, self.spec.params)
        raise ValueError(f"template inconnu: {tmpl}")


def _run_regex(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    pattern = re.compile(str(params.get("pattern", "")))
    workspace = inputs["workspace"]
    manifest = inputs.get("manifest") or workspace.manifest()
    matches: list[dict[str, Any]] = []
    for m in manifest:
        path = str(m.get("path", ""))
        try:
            content = workspace.read(path)
        except FileNotFoundError:
            continue
        for match in pattern.finditer(content):
            matches.append({"path": path, "match": match.group(0)[:120]})
            if len(matches) >= 50:
                break
    return {"template": "regex_scanner",
            "pattern": pattern.pattern,
            "matches_count": len(matches),
            "sample": matches[:10]}


def _run_file_counter(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    suffix = str(params.get("suffix", ".py"))
    manifest = inputs.get("manifest") or inputs["workspace"].manifest()
    n = sum(1 for m in manifest if str(m.get("path", "")).endswith(suffix))
    return {"template": "file_counter", "suffix": suffix, "count": n}


def _run_grepper(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    needle = str(params.get("needle", ""))
    workspace = inputs["workspace"]
    manifest = inputs.get("manifest") or workspace.manifest()
    hits: list[dict[str, Any]] = []
    for m in manifest:
        path = str(m.get("path", ""))
        try:
            for i, line in enumerate(workspace.read(path).splitlines(), 1):
                if needle in line:
                    hits.append({"path": path, "line": i, "excerpt": line.strip()[:120]})
                    if len(hits) >= 40:
                        break
        except FileNotFoundError:
            continue
    return {"template": "content_grepper", "needle": needle,
            "hits_count": len(hits), "sample": hits[:10]}


def _run_json_extract(inputs: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    import json
    path = str(params.get("file", ""))
    jpath = str(params.get("json_path", "")).strip(".")
    content = inputs["workspace"].read(path)
    data: Any = json.loads(content)
    for part in jpath.split("."):
        if not part:
            continue
        if isinstance(data, dict):
            data = data.get(part)
        elif isinstance(data, list) and part.isdigit():
            data = data[int(part)]
        else:
            data = None
            break
    return {"template": "json_extractor", "file": path, "path": jpath, "value": data}


def create_and_register(agent_id: str, spec: EphemeralSpec) -> EphemeralAgent:
    """Cree un agent et l'enregistre dans le registre courant."""
    if spec.template not in ALLOWED_TEMPLATES:
        raise ValueError(f"Template ephemere non autorise: {spec.template}")
    reg = AgentRegistry.get_instance()
    # pylint: disable=protected-access
    if agent_id in reg._agents:
        raise ValueError(f"Agent id deja pris: {agent_id}")
    agent = EphemeralAgent(agent_id, spec)
    reg._agents[agent_id] = agent
    logger.info("ephemeral agent registered: %s (template=%s)", agent_id, spec.template)
    return agent


def dispose(agent_id: str) -> bool:
    """Retire un agent ephemere du registre."""
    reg = AgentRegistry.get_instance()
    # pylint: disable=protected-access
    if agent_id in reg._agents and isinstance(reg._agents[agent_id], EphemeralAgent):
        del reg._agents[agent_id]
        logger.info("ephemeral agent disposed: %s", agent_id)
        return True
    return False
