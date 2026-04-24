"""Knowledge Graph V5.8 (NetworkX wrapper + persistence SQL).

Noeuds (enum EntityType) :
    ENTITY, RULE, DECISION, EVIDENCE, DOMAIN, AGENT, FEATURE_FLAG, TASK

Relations :
    depends_on, contradicts, supports, learned_from, derived_from,
    applies_to, triggers, impacts

Persistence :
    - kg_nodes (PK = id string)
    - kg_edges (source_id, target_id, relation_type unique)

Queries :
    - "Pourquoi X ?"   : path to X via 'supports'/'derived_from'
    - "Contradictions" : edges relation_type='contradicts'
    - "Impact d'un changement" : successors via 'impacts'
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

import asyncpg
import networkx as nx

logger = logging.getLogger("uba.intelligence.knowledge_graph")


class EntityType(str, Enum):
    ENTITY = "entity"
    RULE = "rule"
    DECISION = "decision"
    EVIDENCE = "evidence"
    DOMAIN = "domain"
    AGENT = "agent"
    FEATURE_FLAG = "feature_flag"
    TASK = "task"


class RelationType(str, Enum):
    DEPENDS_ON = "depends_on"
    CONTRADICTS = "contradicts"
    SUPPORTS = "supports"
    LEARNED_FROM = "learned_from"
    DERIVED_FROM = "derived_from"
    APPLIES_TO = "applies_to"
    TRIGGERS = "triggers"
    IMPACTS = "impacts"


@dataclass
class KGNode:
    id: str
    node_type: EntityType
    label: str
    attributes: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "label": self.label,
            "attributes": self.attributes,
        }


@dataclass
class KGEdge:
    source_id: str
    target_id: str
    relation_type: RelationType
    weight: float = 1.0
    attributes: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "weight": self.weight,
            "attributes": self.attributes or {},
        }


class KnowledgeGraph:
    """NetworkX DiGraph avec persistence SQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ----- CRUD Nodes -----

    async def add_node(
        self, node_id: str, node_type: EntityType, label: str,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_nodes(id, node_type, label, attributes)
                VALUES ($1, $2, $3, $4::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    label = EXCLUDED.label,
                    attributes = EXCLUDED.attributes,
                    updated_at = NOW()
                """,
                node_id, node_type.value, label,
                json.dumps(attributes or {}),
            )

    async def get_node(self, node_id: str) -> KGNode | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, node_type, label, attributes FROM kg_nodes "
                "WHERE id = $1", node_id,
            )
        if row is None:
            return None
        return KGNode(
            id=row["id"],
            node_type=EntityType(row["node_type"]),
            label=row["label"],
            attributes=_json(row["attributes"]) or {},
        )

    async def delete_node(self, node_id: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM kg_nodes WHERE id = $1", node_id)

    # ----- CRUD Edges -----

    async def add_edge(
        self, source_id: str, target_id: str,
        relation_type: RelationType, weight: float = 1.0,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO kg_edges
                    (source_id, target_id, relation_type, weight, attributes)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (source_id, target_id, relation_type)
                DO UPDATE SET
                    weight = EXCLUDED.weight,
                    attributes = EXCLUDED.attributes
                """,
                source_id, target_id, relation_type.value, weight,
                json.dumps(attributes or {}),
            )

    # ----- Queries -----

    async def get_neighbors(
        self, node_id: str, relation: RelationType | None = None,
        direction: str = "outgoing",
    ) -> list[dict[str, Any]]:
        """Voisins (incoming/outgoing/both)."""
        conditions = ["source_id = $1" if direction in ("outgoing", "both")
                      else "target_id = $1"]
        if direction == "both":
            conditions = ["(source_id = $1 OR target_id = $1)"]
        params: list[Any] = [node_id]
        if relation:
            conditions.append("relation_type = $2")
            params.append(relation.value)
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT e.source_id, e.target_id, e.relation_type, e.weight,
                       e.attributes
                FROM kg_edges e
                WHERE {' AND '.join(conditions)}
                """,
                *params,
            )
        return [
            {
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "relation_type": r["relation_type"],
                "weight": float(r["weight"]),
                "attributes": _json(r["attributes"]) or {},
            } for r in rows
        ]

    async def _build_nx_graph(
        self, node_types: Iterable[str] | None = None,
    ) -> nx.MultiDiGraph:
        """Construit un NetworkX DiGraph depuis la BDD."""
        g: nx.MultiDiGraph = nx.MultiDiGraph()
        async with self.pool.acquire() as conn:
            if node_types:
                nodes = await conn.fetch(
                    "SELECT id, node_type, label FROM kg_nodes "
                    "WHERE node_type = ANY($1::text[])",
                    list(node_types),
                )
            else:
                nodes = await conn.fetch(
                    "SELECT id, node_type, label FROM kg_nodes",
                )
            edges = await conn.fetch(
                """
                SELECT source_id, target_id, relation_type, weight
                FROM kg_edges
                """,
            )
        for n in nodes:
            g.add_node(n["id"], node_type=n["node_type"], label=n["label"])
        for e in edges:
            if e["source_id"] in g and e["target_id"] in g:
                g.add_edge(e["source_id"], e["target_id"],
                           relation=e["relation_type"],
                           weight=float(e["weight"]))
        return g

    async def shortest_path(
        self, source: str, target: str,
    ) -> list[str] | None:
        g = await self._build_nx_graph()
        if source not in g or target not in g:
            return None
        try:
            return nx.shortest_path(g, source, target)
        except nx.NetworkXNoPath:
            return None

    async def subgraph(
        self, node_id: str, depth: int = 2,
    ) -> dict[str, Any]:
        """Subgraph ego autour de node_id jusqu a depth."""
        g = await self._build_nx_graph()
        if node_id not in g:
            return {"nodes": [], "edges": []}
        undirected = g.to_undirected()
        nodes = nx.single_source_shortest_path_length(
            undirected, node_id, cutoff=depth,
        )
        sub = g.subgraph(nodes.keys())
        return {
            "nodes": [
                {"id": n, **sub.nodes[n]} for n in sub.nodes
            ],
            "edges": [
                {"source": u, "target": v, **d}
                for u, v, d in sub.edges(data=True)
            ],
        }

    async def centrality(
        self, node_id: str | None = None,
    ) -> dict[str, float]:
        g = await self._build_nx_graph()
        if not g.nodes:
            return {}
        # degree centrality (fast)
        centrality = nx.degree_centrality(g)
        if node_id:
            return {node_id: centrality.get(node_id, 0.0)}
        return centrality

    async def contradictions(self) -> list[dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.source_id, e.target_id, e.weight,
                       n1.label AS source_label,
                       n2.label AS target_label
                FROM kg_edges e
                JOIN kg_nodes n1 ON n1.id = e.source_id
                JOIN kg_nodes n2 ON n2.id = e.target_id
                WHERE e.relation_type = 'contradicts'
                ORDER BY e.weight DESC
                """,
            )
        return [
            {
                "source_id": r["source_id"],
                "source_label": r["source_label"],
                "target_id": r["target_id"],
                "target_label": r["target_label"],
                "weight": float(r["weight"]),
            } for r in rows
        ]

    async def export(self) -> dict[str, Any]:
        """Export full graph en format D3.js."""
        async with self.pool.acquire() as conn:
            nodes = await conn.fetch(
                "SELECT id, node_type, label, attributes FROM kg_nodes",
            )
            edges = await conn.fetch(
                "SELECT source_id, target_id, relation_type, weight "
                "FROM kg_edges",
            )
        return {
            "nodes": [
                {"id": n["id"], "group": n["node_type"], "label": n["label"],
                 "attributes": _json(n["attributes"]) or {}}
                for n in nodes
            ],
            "links": [
                {"source": e["source_id"], "target": e["target_id"],
                 "relation": e["relation_type"], "value": float(e["weight"])}
                for e in edges
            ],
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    async def stats(self) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            node_count = await conn.fetchval("SELECT COUNT(*) FROM kg_nodes")
            edge_count = await conn.fetchval("SELECT COUNT(*) FROM kg_edges")
            by_type = await conn.fetch(
                "SELECT node_type, COUNT(*) AS n FROM kg_nodes "
                "GROUP BY node_type",
            )
            by_relation = await conn.fetch(
                "SELECT relation_type, COUNT(*) AS n FROM kg_edges "
                "GROUP BY relation_type",
            )
        return {
            "nodes_total": int(node_count),
            "edges_total": int(edge_count),
            "nodes_by_type": {r["node_type"]: int(r["n"]) for r in by_type},
            "edges_by_relation": {
                r["relation_type"]: int(r["n"]) for r in by_relation
            },
        }


def _json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


# ============================================================================
# Auto-population helpers (hooks)
# ============================================================================

async def populate_from_domains(kg: KnowledgeGraph) -> dict[str, int]:
    """Seed graph depuis les 5 domaines + leurs rules + feature flags."""
    from app.core import DomainRegistry
    from app.domains import RULES_ENGINE

    counts = {"domains": 0, "rules": 0, "flags": 0, "edges": 0}
    reg = DomainRegistry.instance()
    domains = reg.list_domains()

    for d in domains:
        domain_id = d["domain_id"]
        await kg.add_node(
            node_id=f"domain:{domain_id}",
            node_type=EntityType.DOMAIN,
            label=domain_id,
            attributes={"version": d["latest_version"],
                        "description": d["description"]},
        )
        counts["domains"] += 1
        # Rules du domaine
        for rule in RULES_ENGINE.get_rules(domain_id):
            rule_id = f"rule:{rule.id}"
            await kg.add_node(
                node_id=rule_id,
                node_type=EntityType.RULE,
                label=rule.description or rule.id,
                attributes={"priority": rule.priority,
                            "enabled": rule.enabled,
                            "version": rule.version},
            )
            await kg.add_edge(
                source_id=rule_id,
                target_id=f"domain:{domain_id}",
                relation_type=RelationType.APPLIES_TO,
                weight=1.0,
            )
            counts["rules"] += 1
            counts["edges"] += 1

    return counts
