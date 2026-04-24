"""V5.4 - Tree of Thoughts (Yao 2023).

DFS / BFS / best_first strategies. Pruning sur value.
"""
from __future__ import annotations

import heapq
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.cognition.reasoning_trace_models import TreeNode, TreeTrace

EVAL_WEIGHTS = {"faisabilite": 0.3, "progres": 0.3,
                 "correction": 0.3, "novelty": 0.1}


def evaluate_thought(
    thought: str, *, context: dict[str, Any] | None = None,
) -> float:
    if not thought:
        return 0.0
    length_score = min(1.0, len(thought) / 400)
    keyword_density = 0.0
    for kw in ("donc", "parce que", "therefore", "because", "ainsi"):
        if kw in thought.lower():
            keyword_density += 0.15
    keyword_density = min(1.0, keyword_density)
    faisabilite = 0.7 + 0.3 * length_score
    progres = 0.5 + 0.5 * keyword_density
    correction = 0.6 + 0.4 * length_score
    novelty = 0.5
    return (EVAL_WEIGHTS["faisabilite"] * faisabilite
            + EVAL_WEIGHTS["progres"] * progres
            + EVAL_WEIGHTS["correction"] * correction
            + EVAL_WEIGHTS["novelty"] * novelty)


@dataclass
class InternalNode:
    id: str
    parent: str | None
    depth: int
    thought: str
    value: float
    children: list[str] = field(default_factory=list)
    pruned: bool = False


def generate_thoughts(
    parent_thought: str, branching: int = 3, *,
    generator: Callable[[str, int], list[str]] | None = None,
) -> list[str]:
    if generator is None:
        generator = _default_generator
    return generator(parent_thought, branching)


def _default_generator(parent: str, k: int) -> list[str]:
    return [f"child_{i}_of<{parent[:40]}>" for i in range(k)]


def _make_expander(
    registry: dict[str, InternalNode], *,
    max_depth: int, branching: int, prune_threshold: float,
    generator: Callable[[str, int], list[str]] | None,
) -> Callable[[InternalNode], list[InternalNode]]:
    def _expand(node: InternalNode) -> list[InternalNode]:
        if node.depth >= max_depth:
            return []
        kids_text = generate_thoughts(node.thought, branching, generator=generator)
        kids: list[InternalNode] = []
        for i, txt in enumerate(kids_text):
            nid = f"{node.id}.{i}"
            v = evaluate_thought(txt)
            child = InternalNode(id=nid, parent=node.id,
                                  depth=node.depth + 1,
                                  thought=txt, value=v)
            if v < prune_threshold:
                child.pruned = True
            registry[nid] = child
            node.children.append(nid)
            kids.append(child)
        return kids
    return _expand


def _traverse_dfs(root, expand) -> None:
    stack = [root]
    while stack:
        n = stack.pop()
        if n.pruned:
            continue
        stack.extend(expand(n))


def _traverse_bfs(root, expand) -> None:
    queue = [root]
    while queue:
        n = queue.pop(0)
        if n.pruned:
            continue
        queue.extend(expand(n))


def _traverse_best_first(root, registry, expand) -> None:
    heap: list[tuple[float, str]] = [(-root.value, root.id)]
    while heap:
        _, nid = heapq.heappop(heap)
        n = registry[nid]
        if n.pruned:
            continue
        for k in expand(n):
            heapq.heappush(heap, (-k.value, k.id))


def _best_path(root, registry) -> list[str]:
    path = [root.id]
    cur = root
    while cur.children:
        alive = [registry[cid] for cid in cur.children if not registry[cid].pruned]
        if not alive:
            break
        best = max(alive, key=lambda n: n.value)
        path.append(best.id)
        cur = best
    return path


def build_tree(
    root_thought: str, *,
    strategy: str = "best_first",
    max_depth: int = 4, branching: int = 3,
    prune_threshold: float = 0.40,
    generator: Callable[[str, int], list[str]] | None = None,
) -> TreeTrace:
    if strategy not in ("dfs", "bfs", "best_first", "mcts"):
        raise ValueError(f"strategy inconnue: {strategy}")
    root = InternalNode(
        id="root", parent=None, depth=0,
        thought=root_thought, value=evaluate_thought(root_thought),
    )
    registry: dict[str, InternalNode] = {root.id: root}
    expand = _make_expander(
        registry, max_depth=max_depth, branching=branching,
        prune_threshold=prune_threshold, generator=generator,
    )
    if strategy == "dfs":
        _traverse_dfs(root, expand)
    elif strategy == "bfs":
        _traverse_bfs(root, expand)
    else:
        _traverse_best_first(root, registry, expand)

    path = _best_path(root, registry)
    final_score = registry[path[-1]].value if path else 0.0
    nodes = [TreeNode(
        node_id=n.id, parent_id=n.parent, depth=n.depth,
        thought=n.thought, value=n.value, pruned=n.pruned,
    ) for n in registry.values()]
    return TreeTrace(
        strategy=strategy, max_depth=max_depth, branching_factor=branching,
        nodes=nodes, best_path=path, final_score=final_score,
    )
