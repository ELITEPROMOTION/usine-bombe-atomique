"""Agent #01 Claude Code - generation de code pilotee par le Tri-Cerveau V2.

Le Builder de Tri-Cerveau delegue a l'un des chemins :
1. `ANTHROPIC_API_KEY` presente : requete Anthropic (messages API) avec une
   prompt systeme demandant un JSON structure {files: {path: content}}.
2. Pas de cle : fallback deterministe base sur templates (suffisant pour
   tester l'orchestrateur bout-en-bout et generer une Classe A simple CRUD).

Le builder recoit optionnellement la liste d'issues du Critic pour raffiner.
"""
from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.workspace import Workspace
from app.config import get_settings
from app.database import get_pool
from app.orchestration.context_optimizer import optimize as optimize_context
from app.orchestration.cost_optimizer import record_actual_usage, select_model
from app.orchestration.prompt_ab import pick_variant, record_outcome
from app.orchestration.tri_brain import CriticIssue, run_tri_brain

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Tu es un generateur de code senior. A partir d'une specification, tu produis un
projet Python/FastAPI minimal et fonctionnel. Reponds UNIQUEMENT avec un JSON valide :
{"files": {"<chemin relatif>": "<contenu texte>", ...}}.
Contraintes : code ruff-clean, tests pytest dans tests/, requirements.txt, README.md."""

REFINE_HINT = """On te repasse la tache car le reviewer a releve des defauts. Corrige les points
ci-dessous en reproduisant tout le projet corrige. Reponds UNIQUEMENT avec le JSON complet."""


class ClaudeCodeAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(agent_id="agent-01-claude-code", name="Claude Code", version="2.0.0")
        self.category = "development"

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        spec: str = inputs["spec"]
        priority: str = inputs.get("priority", "high")
        task_id: str = inputs.get("task_id", "")
        workspace: Workspace = inputs["workspace"]

        # Selection du tier modele (Haiku/Sonnet/Opus) selon la tache
        selection = select_model(spec=spec, priority=priority, refinement_round=0)
        logger.info("cost_optimizer tier=%s model=%s cost~=%.4f USD rationale=%s",
                    selection.tier, selection.model_id,
                    selection.estimated_cost_usd, selection.rationale)

        # Tirage de la variante de system prompt (A/B) - defensif si pas de pool
        pool = None
        with contextlib.suppress(RuntimeError):  # test context sans BDD initialisee
            pool = get_pool()
        variant, chosen_prompt = (None, None)
        if pool is not None:
            try:
                variant, chosen_prompt = await pick_variant(
                    pool, "agent-01-claude-code", default_prompt=SYSTEM_PROMPT,
                )
            except Exception as exc:
                logger.warning("pick_variant failed: %s", exc)
        system_prompt = chosen_prompt or SYSTEM_PROMPT
        variant_id = variant.id if variant else None
        variant_name = variant.variant_name if variant else "default"

        round_counter = {"n": 0}

        async def builder(spec_in: str, prior_issues: list[CriticIssue] | None) -> dict[str, str]:
            if prior_issues:
                round_counter["n"] += 1
            settings = get_settings()
            full_spec = spec_in
            if prior_issues:
                critique = "\n".join(
                    f"- [{i.severity}:{i.category}] {i.message}"
                    + (f" (@{i.path})" if i.path else "")
                    for i in prior_issues[:20]
                )
                full_spec = f"{spec_in}\n\n{REFINE_HINT}\n{critique}"
            if settings.ANTHROPIC_API_KEY:
                try:
                    # Pour un refinement, on escalade eventuellement vers Opus
                    runtime_selection = select_model(
                        spec=spec_in, priority=priority,
                        refinement_round=round_counter["n"],
                    ) if round_counter["n"] else selection
                    # V4.1 context_optimizer : compresser le prompt
                    opt = optimize_context(full_spec)
                    logger.info("context_optimizer saved %d tokens (-%.1f%%)",
                                opt.tokens_saved, opt.compression_pct)
                    files = await _generate_with_anthropic(
                        opt.optimized, settings,
                        model_id=runtime_selection.model_id,
                        system_prompt=system_prompt,
                    )
                    # Enregistre la conso reelle (approx par selection si non fournie)
                    if task_id and pool is not None:
                        try:
                            await record_actual_usage(
                                pool, task_id=task_id,
                                agent_id="agent-01-claude-code",
                                model_id=runtime_selection.model_id,
                                tokens_input=runtime_selection.estimated_input_tokens,
                                tokens_output=runtime_selection.estimated_output_tokens,
                                latency_ms=0,
                            )
                        except Exception as exc:
                            logger.warning("record_actual_usage failed: %s", exc)
                    return files
                except Exception as exc:
                    logger.warning("Anthropic failed, template fallback: %s", exc)
            return _generate_template(spec_in)

        report = await run_tri_brain(spec=spec, workspace=workspace, builder=builder, max_rounds=1)
        manifest = workspace.manifest()

        # Score surrogate pour A/B : 1.0 si approve, 0.5 si refine, 0.0 si reject
        ab_score = {"approve": 1.0, "refine": 0.5, "reject": 0.0}.get(report.final_verdict, 0.5)
        if variant_id and pool is not None:
            try:
                await record_outcome(pool, variant_id, score=ab_score,
                                     won=(report.final_verdict == "approve"))
            except Exception as exc:
                logger.warning("record_outcome failed: %s", exc)

        return {
            "source": report.builder_source,
            "files_count": report.files_count,
            "manifest": manifest,
            "model_selection": {
                "tier": selection.tier,
                "model_id": selection.model_id,
                "estimated_cost_usd": selection.estimated_cost_usd,
                "rationale": selection.rationale,
            },
            "prompt_variant": {"name": variant_name, "id": variant_id},
            "tri_brain": {
                "rounds": report.rounds,
                "final_verdict": report.final_verdict,
                "critic_issues_count": len(report.critic_issues),
                "judge_history": [
                    {
                        "verdict": d.verdict,
                        "critical": d.critical_count,
                        "major": d.major_count,
                        "minor": d.minor_count,
                    } for d in report.judge_history
                ],
            },
        }


async def _generate_with_anthropic(
    spec: str,
    settings: Any,
    model_id: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, str]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    msg = await client.messages.create(
        model=model_id or settings.ANTHROPIC_MODEL,
        max_tokens=16000,
        system=system_prompt or SYSTEM_PROMPT,
        messages=[{"role": "user", "content": spec}],
    )
    from anthropic.types import TextBlock
    text = "".join(block.text for block in msg.content if isinstance(block, TextBlock))
    payload = _extract_json(text)
    files = payload.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("Anthropic response missing 'files' dict")
    return {str(k): str(v) for k, v in files.items()}


def _extract_json(text: str) -> dict[str, Any]:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else text[text.find("{") : text.rfind("}") + 1]
    return json.loads(raw)


def _generate_template(spec: str) -> dict[str, str]:
    resource = _detect_resource(spec)
    singular = resource.lower()
    plural = singular + "s"
    cls = resource.capitalize()

    pkg_init = '"""Generated package."""\n'
    main_py = f'''"""CRUD API - {cls}."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="{cls} API")

_store: dict[int, dict] = {{}}
_next_id: int = 1


class {cls}In(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class {cls}Out({cls}In):
    id: int


@app.get("/health")
def health() -> dict:
    return {{"status": "ok"}}


@app.post("/{plural}", response_model={cls}Out, status_code=201)
def create(payload: {cls}In) -> {cls}Out:
    global _next_id
    item = {{"id": _next_id, **payload.model_dump()}}
    _store[_next_id] = item
    _next_id += 1
    return {cls}Out(**item)


@app.get("/{plural}", response_model=list[{cls}Out])
def list_all() -> list[{cls}Out]:
    return [{cls}Out(**v) for v in _store.values()]


@app.get("/{plural}/{{item_id}}", response_model={cls}Out)
def get_one(item_id: int) -> {cls}Out:
    item = _store.get(item_id)
    if item is None:
        raise HTTPException(404, "{cls} not found")
    return {cls}Out(**item)


@app.put("/{plural}/{{item_id}}", response_model={cls}Out)
def update(item_id: int, payload: {cls}In) -> {cls}Out:
    if item_id not in _store:
        raise HTTPException(404, "{cls} not found")
    updated = {{"id": item_id, **payload.model_dump()}}
    _store[item_id] = updated
    return {cls}Out(**updated)


@app.delete("/{plural}/{{item_id}}", status_code=204)
def delete(item_id: int) -> None:
    if item_id not in _store:
        raise HTTPException(404, "{cls} not found")
    del _store[item_id]
'''

    test_py = f'''"""Tests CRUD {cls}."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {{"status": "ok"}}


def test_crud_cycle() -> None:
    r = client.post("/{plural}", json={{"name": "alpha"}})
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "alpha"
    item_id = item["id"]

    r = client.get(f"/{plural}/{{item_id}}")
    assert r.status_code == 200

    r = client.put(f"/{plural}/{{item_id}}", json={{"name": "beta"}})
    assert r.status_code == 200
    assert r.json()["name"] == "beta"

    r = client.get("/{plural}")
    assert r.status_code == 200
    assert len(r.json()) >= 1

    r = client.delete(f"/{plural}/{{item_id}}")
    assert r.status_code == 204

    r = client.get(f"/{plural}/{{item_id}}")
    assert r.status_code == 404
'''

    requirements = "fastapi==0.115.0\nuvicorn[standard]==0.32.0\npydantic==2.9.2\nhttpx==0.27.2\n"
    pytest_ini = "[pytest]\naddopts = -ra --strict-markers\ntestpaths = tests\n"
    readme_stub = f"# {cls} API\n\nGenerated from spec.\n"

    return {
        "app/__init__.py": pkg_init,
        "app/main.py": main_py,
        "tests/__init__.py": "",
        "tests/test_crud.py": test_py,
        "requirements.txt": requirements,
        "pytest.ini": pytest_ini,
        "README.md": readme_stub,
    }


def _detect_resource(spec: str) -> str:
    lowered = spec.lower()
    for candidate in ("product", "produit", "user", "utilisateur", "item",
                      "article", "book", "order", "task", "customer"):
        if candidate in lowered:
            mapping = {
                "produit": "product",
                "utilisateur": "user",
            }
            return mapping.get(candidate, candidate)
    m = re.search(r"\b([a-zA-Z]{3,20})\b", spec)
    return (m.group(1).lower() if m else "item")
