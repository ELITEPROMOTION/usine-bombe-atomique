"""Tests du DAG orchestrator : topologie, vagues, contexte partage."""
import pytest

from app.orchestrator import DagNode, default_dag, topological_waves


def test_default_dag_has_expected_nodes():
    ids = {n.agent_id for n in default_dag()}
    expected = {
        "agent-01-claude-code", "agent-02-sonarqube", "agent-03-terraform",
        "agent-04-pytest", "agent-05-datadog", "agent-06-docker",
        "agent-11-security", "agent-14-linter", "agent-18-conformite-dz",
        "agent-21-readme",
    }
    assert expected.issubset(ids)


def test_topological_waves_groups_parallel_nodes():
    waves = topological_waves(default_dag())
    assert waves[0] == ["agent-01-claude-code"]
    wave2 = set(waves[1])
    assert {"agent-14-linter", "agent-02-sonarqube", "agent-04-pytest",
            "agent-03-terraform", "agent-06-docker",
            "agent-18-conformite-dz"}.issubset(wave2)
    # README doit arriver apres security + datadog
    wave3 = set(waves[2])
    assert {"agent-05-datadog", "agent-11-security"}.issubset(wave3)
    assert waves[-1] == ["agent-21-readme"]


def test_topological_waves_detects_cycle():
    cyclic = [
        DagNode(agent_id="a", depends_on=["b"]),
        DagNode(agent_id="b", depends_on=["a"]),
    ]
    with pytest.raises(ValueError):
        topological_waves(cyclic)


def test_topological_waves_simple_chain():
    dag = [
        DagNode(agent_id="x"),
        DagNode(agent_id="y", depends_on=["x"]),
        DagNode(agent_id="z", depends_on=["y"]),
    ]
    waves = topological_waves(dag)
    assert waves == [["x"], ["y"], ["z"]]
