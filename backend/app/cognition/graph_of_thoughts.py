"""V5.4 - Graph of Thoughts (Besta 2024).

DAG operations : Generate / Aggregate / Refine / Score / Validate.
Detection contradictions + convergences.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.cognition.reasoning_trace_models import GraphTrace


@dataclass
class GNode:
    id: str
    thought: str
    value: float
    parents: list[str] = field(default_factory=list)


@dataclass
class GEdge:
    src: str
    dst: str
    kind: str        # supports | contradicts | aggregates | refines


@dataclass
class GraphBuild:
    nodes: dict[str, GNode] = field(default_factory=dict)
    edges: list[GEdge] = field(default_factory=list)
    next_id: int = 0

    def add(self, thought: str, value: float = 0.5,
             parents: list[str] | None = None) -> str:
        nid = f"n{self.next_id}"
        self.next_id += 1
        self.nodes[nid] = GNode(id=nid, thought=thought, value=value,
                                 parents=list(parents or []))
        return nid

    def link(self, src: str, dst: str, kind: str = "supports") -> None:
        self.edges.append(GEdge(src=src, dst=dst, kind=kind))


def detect_contradictions(g: GraphBuild) -> list[dict[str, Any]]:
    """Contradiction = 2 noeuds lies par 'contradicts' en parallele."""
    return [{"src": e.src, "dst": e.dst}
            for e in g.edges if e.kind == "contradicts"]


def detect_convergences(g: GraphBuild) -> list[dict[str, Any]]:
    """Convergence = noeud avec >= 2 parents 'supports'."""
    parent_counts: dict[str, int] = {}
    for e in g.edges:
        if e.kind == "supports":
            parent_counts[e.dst] = parent_counts.get(e.dst, 0) + 1
    return [{"node": nid, "support_count": c}
            for nid, c in parent_counts.items() if c >= 2]


def dominant_paths(g: GraphBuild, top_k: int = 3) -> list[list[str]]:
    """Top-k chemins de valeur cumulee maximum (simple heuristic)."""
    if not g.nodes:
        return []
    ranked = sorted(g.nodes.values(), key=lambda n: -n.value)
    return [[n.id for n in ranked[:top_k]]]


def build_trace(g: GraphBuild) -> GraphTrace:
    return GraphTrace(
        nodes=[{"id": n.id, "thought": n.thought, "value": n.value,
                 "parents": n.parents} for n in g.nodes.values()],
        edges=[{"src": e.src, "dst": e.dst, "kind": e.kind}
               for e in g.edges],
        contradictions=detect_contradictions(g),
        convergences=detect_convergences(g),
        dominant_paths=dominant_paths(g),
    )


def aggregate(g: GraphBuild, node_ids: list[str]) -> str:
    """Operation Aggregate : fusionne plusieurs noeuds en un seul."""
    if len(node_ids) < 2:
        raise ValueError("aggregate needs >= 2 nodes")
    thoughts = [g.nodes[nid].thought for nid in node_ids if nid in g.nodes]
    values = [g.nodes[nid].value for nid in node_ids if nid in g.nodes]
    merged = " | ".join(thoughts)[:600]
    avg = sum(values) / len(values) if values else 0.5
    new_id = g.add(merged, value=avg, parents=node_ids)
    for src in node_ids:
        g.link(src, new_id, kind="aggregates")
    return new_id


def refine(g: GraphBuild, node_id: str, refined_thought: str) -> str:
    """Operation Refine : produit un noeud enfant ameliore."""
    if node_id not in g.nodes:
        raise KeyError(node_id)
    parent = g.nodes[node_id]
    new_id = g.add(refined_thought, value=min(1.0, parent.value + 0.10),
                    parents=[node_id])
    g.link(node_id, new_id, kind="refines")
    return new_id
