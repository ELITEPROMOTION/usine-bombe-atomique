"""Agent #21 README Generator - produit un README.md a partir du manifest.

Ne depend pas de la LLM : lit la specification et la liste des artefacts,
genere une doc structuree (sections : Specification, Structure, Installation,
Endpoints, Tests).
"""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace


class ReadmeAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-21-readme", name="README Gen", version="1.0.0")
        self.category = "documentation"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        workspace: Workspace = inputs["workspace"]
        spec: str = inputs.get("spec", "")
        manifest: list[dict[str, Any]] = inputs.get("manifest", []) or workspace.manifest()

        title = _title_from_spec(spec)
        body = _render(title, spec, manifest)
        workspace.write("README.md", body)

        return {
            "path": "README.md",
            "bytes": len(body.encode("utf-8")),
            "sections": 5,
        }


def _title_from_spec(spec: str) -> str:
    first_line = (spec.strip().splitlines() or ["Projet genere"])[0]
    return first_line[:80].rstrip(" .:") or "Projet genere"


def _render(title: str, spec: str, manifest: list[dict[str, Any]]) -> str:
    tree = "\n".join(f"- `{m['path']}` ({m.get('language','?')}, {m.get('size_bytes',0)} o)"
                     for m in manifest)
    has_reqs = any(m["path"] == "requirements.txt" for m in manifest)
    has_tests = any(str(m.get("type")) == "test" for m in manifest)
    has_main = any(m["path"].endswith("app/main.py") or m["path"] == "main.py" for m in manifest)

    install = "```bash\npip install -r requirements.txt\n```\n" if has_reqs else ""
    run = "```bash\nuvicorn app.main:app --reload\n```\n" if has_main else ""
    tests_cmd = "```bash\npytest -q\n```\n" if has_tests else "_Aucun test detecte._\n"

    return f"""# {title}

## Specification

{spec.strip() or "_(vide)_"}

## Structure

{tree or "_Aucun artefact._"}

## Installation

{install or "_Aucune dependance declaree._"}

## Utilisation

{run or "_Aucun point d'entree detecte._"}

## Tests

{tests_cmd}
"""
