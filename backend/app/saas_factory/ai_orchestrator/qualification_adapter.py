"""Adapte `AIRouter` au Protocol `qualification_engine.ClaudeProvider`.

Phase 9C avait defini `QualificationEngine` avec une dependance sur
`ClaudeProvider.analyze_cdc(cdc_text, system_prompt, max_tokens) -> dict`.
Phase 9D apporte `AIRouter.route(prompt, system, project_id, max_tokens)
-> RouterDecision`.

Ce module fait la jonction : `RouterBackedClaudeProvider` implemente
`ClaudeProvider`, recoit un `AIRouter` + `project_id`, et expose
`analyze_cdc(...)`. La sortie attendue est un dict JSON ; on parse le
texte de la reponse (Claude / Perplexity ou autre).
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.saas_factory.ai_orchestrator.router import AIRouter

logger = logging.getLogger(__name__)


class RouterBackedClaudeProvider:
    """Wrap un AIRouter pour satisfaire `qualification_engine.ClaudeProvider`."""

    def __init__(self, router: AIRouter, *, project_id: str) -> None:
        self._router = router
        self._project_id = project_id

    async def analyze_cdc(
        self,
        *,
        cdc_text: str,
        system_prompt: str,
        max_tokens: int = 2000,
    ) -> dict[str, Any]:
        decision = await self._router.route(
            project_id=self._project_id,
            prompt=cdc_text,
            system=system_prompt,
            max_tokens=max_tokens,
        )
        # Le LLM doit avoir produit du JSON strict (cf. SYSTEM_PROMPT 9C).
        text = (decision.response.text or "").strip()
        # Tolerance : si le LLM a entoure de markdown ```json ... ```
        if text.startswith("```"):
            text = text.strip("`")
            # premiere ligne souvent 'json\n'
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
            text = text.rstrip("`").rstrip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"reponse LLM non parsable comme JSON "
                f"(provider={decision.actual_provider}): {exc}"
            ) from exc
