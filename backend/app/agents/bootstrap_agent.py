"""Agent #00 Bootstrap - conforme CDC Ch.11.3.2.

Cet agent n'est PAS un agent metier. Il se contente d'enregistrer
que le bootstrap initial (12 etapes) a ete execute avec succes.
Le code de construction reel vit dans les 12 etapes du script
d'amorcage execute par l'operateur / Agent Bootstrap.
"""
from __future__ import annotations

from typing import Any

from app.agents.base_agent import BaseAgent


class BootstrapAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            agent_id="agent-00-bootstrap",
            name="Bootstrap Agent",
            version="1.0.0",
        )

    async def _execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        return {
            "bootstrap_completed": True,
            "cdc_version": inputs.get("cdc_version", "3.0"),
            "handoff_to": "orchestrator",
        }
