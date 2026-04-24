"""V5.4 - MCTS (Monte Carlo Tree Search) reasoning.

UCB1 : score = exploitation + C * sqrt(ln(N) / n)
C = sqrt(2) default.
"""
from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

DEFAULT_C = math.sqrt(2)


@dataclass
class MctsNode:
    id: str
    parent: str | None
    action: str | None
    visits: int = 0
    total_value: float = 0.0
    children: list[str] = field(default_factory=list)
    terminal: bool = False

    @property
    def mean_value(self) -> float:
        if self.visits == 0:
            return 0.0
        return self.total_value / self.visits


def ucb1(node: MctsNode, parent_visits: int, c: float = DEFAULT_C) -> float:
    if node.visits == 0:
        return float("inf")
    return (node.mean_value
            + c * math.sqrt(math.log(max(1, parent_visits)) / node.visits))


def _default_actions(state: str) -> list[str]:
    return [f"act_{i}" for i in range(3)]


def _default_simulate(state: str, action: str) -> float:
    """Simulation rollout : score deterministe (seed base sur string)."""
    seed = (hash(state) + hash(action)) % 100
    return seed / 100


def _select(root, registry, c):
    node = root
    while node.children and not node.terminal:
        best_child = max(
            (registry[cid] for cid in node.children),
            key=lambda cn: ucb1(cn, node.visits, c),
        )
        node = best_child
    return node


def _expand_if_needed(node, registry, actions_fn, rng):
    if node.terminal or node.visits == 0:
        return node
    kids = actions_fn(node.id)
    for a in kids:
        cid = f"{node.id}/{a}"
        if cid in registry:
            continue
        registry[cid] = MctsNode(id=cid, parent=node.id, action=a)
        node.children.append(cid)
    if node.children:
        return registry[rng.choice(node.children)]
    return node


def _backpropagate(node, registry, value):
    cur = node
    while cur is not None:
        cur.visits += 1
        cur.total_value += value
        cur = registry[cur.parent] if cur.parent else None


@dataclass
class MctsResult:
    best_action: str | None
    best_value: float
    tree_size: int
    simulations: int
    ucb_scores: dict[str, float]


def run_mcts(
    root_state: str, *,
    n_simulations: int = 30,
    c: float = DEFAULT_C,
    actions_fn: Callable[[str], list[str]] | None = None,
    simulate_fn: Callable[[str, str], float] | None = None,
    seed: int = 42,
) -> MctsResult:
    actions_fn = actions_fn or _default_actions
    simulate_fn = simulate_fn or _default_simulate
    rng = random.Random(seed)
    root = MctsNode(id="root", parent=None, action=None)
    registry: dict[str, MctsNode] = {root.id: root}

    for _ in range(n_simulations):
        node = _select(root, registry, c)
        node = _expand_if_needed(node, registry, actions_fn, rng)
        value = simulate_fn(node.id, node.action or "_")
        _backpropagate(node, registry, value)

    # Best action : root's child with highest visits (robust standard)
    if not root.children:
        return MctsResult(
            best_action=None, best_value=0.0,
            tree_size=len(registry), simulations=n_simulations,
            ucb_scores={})
    best_child = max(
        (registry[cid] for cid in root.children),
        key=lambda n: n.visits,
    )
    ucb_scores = {
        registry[cid].action: ucb1(registry[cid], root.visits, c)
        for cid in root.children
    }
    return MctsResult(
        best_action=best_child.action, best_value=best_child.mean_value,
        tree_size=len(registry), simulations=n_simulations,
        ucb_scores=ucb_scores,
    )
