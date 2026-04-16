"""Classe abstraite commune a tous les agents specialises."""
from __future__ import annotations

import abc
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    agent_id: str = ""
    agent_name: str = ""
    status: str = "pending"
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0.0


class BaseAgent(abc.ABC):
    """Cycle de vie: initialize -> execute -> cleanup."""

    def __init__(self, agent_id: str, name: str, version: str = "0.1.0") -> None:
        self.agent_id = agent_id
        self.name = name
        self.version = version
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        await self._initialize()
        self._initialized = True
        logger.info("Agent %s initialized", self.agent_id)

    async def execute(self, inputs: dict[str, Any]) -> AgentResult:
        if not self._initialized:
            await self.initialize()
        start = time.perf_counter()
        try:
            output = await self._execute(inputs)
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.name,
                status="success",
                output=output if isinstance(output, dict) else {"result": output},
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:
            logger.exception("Agent %s failed", self.agent_id)
            return AgentResult(
                agent_id=self.agent_id,
                agent_name=self.name,
                status="failed",
                error=str(exc),
                duration_ms=(time.perf_counter() - start) * 1000,
            )

    async def cleanup(self) -> None:
        """Override si ressources a liberer."""

    async def _initialize(self) -> None:
        """Override si initialisation specifique."""

    @abc.abstractmethod
    async def _execute(self, inputs: dict[str, Any]) -> Any:
        """Implementation metier."""
