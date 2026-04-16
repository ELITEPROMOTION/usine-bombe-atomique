"""Verifie que le registre contient bien les 23 agents (+ bootstrap agent-00)."""
import pytest
from app.agents.registry import AgentRegistry, AGENT_CATALOG


def test_registry_catalog_has_expected_agents():
    ids = {aid for aid, _, _ in AGENT_CATALOG}
    assert "agent-00-bootstrap" in ids
    assert "agent-01-claude-code" in ids
    assert len(ids) == 24  # 23 metier + bootstrap


def test_registry_singleton():
    r1 = AgentRegistry.get_instance()
    r2 = AgentRegistry.get_instance()
    assert r1 is r2


def test_registry_get_unknown_raises():
    registry = AgentRegistry.get_instance()
    with pytest.raises(KeyError):
        registry.get("agent-99-inexistant")


@pytest.mark.asyncio
async def test_registry_initialize_all():
    registry = AgentRegistry.get_instance()
    await registry.initialize_all()
    for info in registry.list_all():
        assert info["initialized"] is True
