"""V5.4 - ReAct Engine (Yao 2022) avec 8 outils.

Thought -> Action -> Observation -> Thought ... Max 10 iterations.
Anti-repetition : meme action 2x de suite -> escalate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


AVAILABLE_TOOLS = {
    "search_web", "query_bdd", "calculate", "read_file",
    "run_test", "ask_memory", "check_truth", "consult_source",
}

MAX_ITERATIONS = 10


@dataclass
class Step:
    index: int
    thought: str
    action: str | None = None
    action_input: dict[str, Any] | None = None
    observation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index, "thought": self.thought,
            "action": self.action, "action_input": self.action_input,
            "observation": self.observation,
        }


@dataclass
class ReactResult:
    steps: list[Step]
    final_answer: str | None
    converged: bool
    stop_reason: str
    repeated_action: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "converged": self.converged,
            "stop_reason": self.stop_reason,
            "repeated_action": self.repeated_action,
        }


def _default_tool_dispatch(name: str, args: dict[str, Any]) -> str:
    """Dispatcher par defaut (deterministe, pour tests)."""
    return f"[stub:{name}] args={list(args.keys())}"


async def run(
    problem: str, *,
    tool_dispatcher: Callable[[str, dict[str, Any]], str] | None = None,
    policy: Callable[[list[Step]], Step | None] | None = None,
    max_iterations: int = MAX_ITERATIONS,
) -> ReactResult:
    """Execute la boucle ReAct."""
    if tool_dispatcher is None:
        tool_dispatcher = _default_tool_dispatch
    if policy is None:
        policy = _default_policy

    steps: list[Step] = []
    last_actions: list[str] = []
    repeated = False
    converged = False
    stop_reason = "max_iterations"

    for i in range(max_iterations):
        proposal = policy(steps)
        if proposal is None:
            stop_reason = "policy_no_action"
            break
        # Set proper index
        proposal = Step(
            index=i, thought=proposal.thought,
            action=proposal.action,
            action_input=proposal.action_input,
        )
        # Anti-repetition
        if proposal.action and last_actions[-1:] == [proposal.action]:
            repeated_consecutive = len(last_actions) >= 2 and all(
                a == proposal.action for a in last_actions[-2:])
            if repeated_consecutive:
                repeated = True
                stop_reason = "repeated_action_escalate"
                steps.append(proposal)
                break

        if proposal.action is None:
            # final answer
            converged = True
            stop_reason = "converged"
            steps.append(proposal)
            break

        if proposal.action not in AVAILABLE_TOOLS:
            stop_reason = f"unknown_tool:{proposal.action}"
            steps.append(proposal)
            break

        proposal.observation = tool_dispatcher(proposal.action,
                                                proposal.action_input or {})
        steps.append(proposal)
        last_actions.append(proposal.action)

    final = None
    if converged and steps:
        final = steps[-1].thought
    return ReactResult(
        steps=steps, final_answer=final, converged=converged,
        stop_reason=stop_reason, repeated_action=repeated,
    )


def _default_policy(steps: list[Step]) -> Step | None:
    """Policy deterministe pour tests : alternance pensee/action/final."""
    i = len(steps)
    if i == 0:
        return Step(index=0, thought="start exploration",
                    action="ask_memory",
                    action_input={"question": "relevant patterns"})
    if i == 1:
        return Step(index=1, thought="check truth",
                    action="check_truth",
                    action_input={"claim": "hypothesis A"})
    # final answer
    return Step(index=i, thought=f"Conclusion after {i} observations",
                action=None, action_input=None)
