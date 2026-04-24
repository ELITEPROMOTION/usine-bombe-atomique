"""Tests knowledge graph V5.8 (NetworkX-powered)."""
from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio

from app.intelligence.knowledge_graph import (
    EntityType, KnowledgeGraph, RelationType, populate_from_domains,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def kg(pool):
    """Graph + cleanup tests nodes after each test."""
    g = KnowledgeGraph(pool)
    created_ids: list[str] = []
    yield (g, created_ids)
    # Cleanup
    async with pool.acquire() as conn:
        for nid in created_ids:
            await conn.execute("DELETE FROM kg_nodes WHERE id = $1", nid)


async def test_add_node(kg) -> None:
    g, created = kg
    nid = f"test_node_{uuid4().hex[:8]}"
    created.append(nid)
    await g.add_node(nid, EntityType.ENTITY, "Test Entity",
                      attributes={"weight": 1.0})
    node = await g.get_node(nid)
    assert node is not None
    assert node.label == "Test Entity"
    assert node.attributes == {"weight": 1.0}


async def test_add_node_upsert(kg) -> None:
    g, created = kg
    nid = f"test_upsert_{uuid4().hex[:8]}"
    created.append(nid)
    await g.add_node(nid, EntityType.RULE, "v1")
    await g.add_node(nid, EntityType.RULE, "v2")  # update
    node = await g.get_node(nid)
    assert node.label == "v2"


async def test_get_node_unknown(kg) -> None:
    g, _ = kg
    node = await g.get_node("nonexistent")
    assert node is None


async def test_add_edge(kg) -> None:
    g, created = kg
    a = f"a_{uuid4().hex[:6]}"
    b = f"b_{uuid4().hex[:6]}"
    created.extend([a, b])
    await g.add_node(a, EntityType.RULE, "Rule A")
    await g.add_node(b, EntityType.RULE, "Rule B")
    await g.add_edge(a, b, RelationType.DEPENDS_ON, weight=0.8)
    neighbors = await g.get_neighbors(a, direction="outgoing")
    assert any(n["target_id"] == b for n in neighbors)


async def test_neighbors_filtered_by_relation(kg) -> None:
    g, created = kg
    a = f"a_{uuid4().hex[:6]}"
    b = f"b_{uuid4().hex[:6]}"
    c = f"c_{uuid4().hex[:6]}"
    created.extend([a, b, c])
    await g.add_node(a, EntityType.RULE, "A")
    await g.add_node(b, EntityType.RULE, "B")
    await g.add_node(c, EntityType.RULE, "C")
    await g.add_edge(a, b, RelationType.DEPENDS_ON)
    await g.add_edge(a, c, RelationType.CONTRADICTS)
    deps = await g.get_neighbors(a, relation=RelationType.DEPENDS_ON)
    contras = await g.get_neighbors(a, relation=RelationType.CONTRADICTS)
    assert len(deps) == 1
    assert len(contras) == 1


async def test_shortest_path(kg) -> None:
    g, created = kg
    a = f"a_{uuid4().hex[:6]}"
    b = f"b_{uuid4().hex[:6]}"
    c = f"c_{uuid4().hex[:6]}"
    created.extend([a, b, c])
    await g.add_node(a, EntityType.RULE, "A")
    await g.add_node(b, EntityType.RULE, "B")
    await g.add_node(c, EntityType.RULE, "C")
    await g.add_edge(a, b, RelationType.DEPENDS_ON)
    await g.add_edge(b, c, RelationType.DEPENDS_ON)
    path = await g.shortest_path(a, c)
    assert path == [a, b, c]


async def test_shortest_path_none(kg) -> None:
    g, created = kg
    a = f"iso_a_{uuid4().hex[:6]}"
    b = f"iso_b_{uuid4().hex[:6]}"
    created.extend([a, b])
    await g.add_node(a, EntityType.RULE, "A")
    await g.add_node(b, EntityType.RULE, "B")
    path = await g.shortest_path(a, b)
    assert path is None


async def test_contradictions_detected(kg) -> None:
    g, created = kg
    a = f"ca_{uuid4().hex[:6]}"
    b = f"cb_{uuid4().hex[:6]}"
    created.extend([a, b])
    await g.add_node(a, EntityType.RULE, "R-a")
    await g.add_node(b, EntityType.RULE, "R-b")
    await g.add_edge(a, b, RelationType.CONTRADICTS, weight=0.9)
    contras = await g.contradictions()
    assert any(c["source_id"] == a and c["target_id"] == b for c in contras)


async def test_subgraph(kg) -> None:
    g, created = kg
    a = f"sg_a_{uuid4().hex[:6]}"
    b = f"sg_b_{uuid4().hex[:6]}"
    c = f"sg_c_{uuid4().hex[:6]}"
    created.extend([a, b, c])
    await g.add_node(a, EntityType.RULE, "A")
    await g.add_node(b, EntityType.RULE, "B")
    await g.add_node(c, EntityType.RULE, "C")
    await g.add_edge(a, b, RelationType.DEPENDS_ON)
    await g.add_edge(b, c, RelationType.DEPENDS_ON)
    sub = await g.subgraph(a, depth=2)
    assert len(sub["nodes"]) == 3
    assert len(sub["edges"]) >= 2


async def test_stats(kg, pool) -> None:
    g, _ = kg
    stats = await g.stats()
    assert "nodes_total" in stats
    assert "edges_total" in stats
    assert stats["nodes_total"] >= 0


async def test_export_format(kg) -> None:
    g, _ = kg
    export = await g.export()
    assert "nodes" in export
    assert "links" in export
    assert "node_count" in export


async def test_populate_from_domains(pool) -> None:
    # Register domains first
    from app.domains import register_all
    register_all()
    g = KnowledgeGraph(pool)
    counts = await populate_from_domains(g)
    assert counts["domains"] >= 5
    assert counts["rules"] >= 30


async def test_migration_031_tables(pool) -> None:
    async with pool.acquire() as conn:
        for tbl in ("kg_nodes", "kg_edges"):
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1)", tbl,
            )
            assert exists


async def test_add_edge_upsert(kg) -> None:
    g, created = kg
    a = f"u_a_{uuid4().hex[:6]}"
    b = f"u_b_{uuid4().hex[:6]}"
    created.extend([a, b])
    await g.add_node(a, EntityType.RULE, "A")
    await g.add_node(b, EntityType.RULE, "B")
    await g.add_edge(a, b, RelationType.DEPENDS_ON, weight=0.5)
    await g.add_edge(a, b, RelationType.DEPENDS_ON, weight=0.9)  # update
    neighbors = await g.get_neighbors(a)
    edge = next(n for n in neighbors if n["target_id"] == b)
    assert edge["weight"] == 0.9


async def test_entity_types_enum() -> None:
    assert EntityType.ENTITY.value == "entity"
    assert EntityType.RULE.value == "rule"
    assert EntityType.DECISION.value == "decision"


async def test_relation_types_enum() -> None:
    assert RelationType.DEPENDS_ON.value == "depends_on"
    assert RelationType.CONTRADICTS.value == "contradicts"
    assert RelationType.SUPPORTS.value == "supports"


async def test_centrality(kg) -> None:
    g, created = kg
    nodes = [f"cn_{i}_{uuid4().hex[:4]}" for i in range(3)]
    created.extend(nodes)
    for n in nodes:
        await g.add_node(n, EntityType.RULE, n)
    await g.add_edge(nodes[0], nodes[1], RelationType.DEPENDS_ON)
    await g.add_edge(nodes[0], nodes[2], RelationType.DEPENDS_ON)
    cent = await g.centrality(nodes[0])
    assert nodes[0] in cent
    assert 0.0 <= cent[nodes[0]] <= 1.0
