"""Tests active learner V5.8."""
from __future__ import annotations

import pytest

from app.intelligence.active_learner import (
    ActiveLearner, DEFAULT_CONFIDENCE_THRESHOLD,
)

pytestmark = pytest.mark.asyncio


async def test_submit_below_threshold_creates_loop(pool) -> None:
    al = ActiveLearner(pool, confidence_threshold=0.7)
    loop_id = await al.submit_loop(
        decision_id=None, domain_id="fiscal_dz",
        input_context={"revenu_annuel": 100},
        original_output={"tranche": 1},
        original_confidence=0.5,
    )
    assert loop_id > 0


async def test_submit_above_threshold_returns_minus_one(pool) -> None:
    al = ActiveLearner(pool, confidence_threshold=0.7)
    loop_id = await al.submit_loop(
        decision_id=None, domain_id="fiscal_dz",
        input_context={"revenu_annuel": 100},
        original_output={"tranche": 1},
        original_confidence=0.95,
    )
    assert loop_id == -1


async def test_list_pending_returns_loops(pool) -> None:
    al = ActiveLearner(pool)
    await al.submit_loop(
        decision_id=None, domain_id="rh",
        input_context={}, original_output={},
        original_confidence=0.3,
    )
    pending = await al.list_pending(domain_id="rh", limit=10)
    assert len(pending) >= 1


async def test_apply_feedback_updates_status(pool) -> None:
    al = ActiveLearner(pool)
    loop_id = await al.submit_loop(
        decision_id=None, domain_id="comptabilite",
        input_context={}, original_output={},
        original_confidence=0.4,
    )
    updated = await al.apply_feedback(
        loop_id=loop_id,
        choice={"choice_index": 0},
        feedback_text="accepte",
        agreement_score=0.85,
        status="accepted",
    )
    assert updated is not None
    assert updated.status == "accepted"
    assert updated.agreement_score == 0.85


async def test_apply_feedback_unknown_loop(pool) -> None:
    al = ActiveLearner(pool)
    updated = await al.apply_feedback(
        loop_id=999_999_999, choice={}, status="rejected",
    )
    assert updated is None


async def test_metrics_computation(pool) -> None:
    al = ActiveLearner(pool)
    # Seed some loops
    for conf, status in [(0.4, "accepted"), (0.5, "rejected"), (0.3, "accepted")]:
        lid = await al.submit_loop(
            decision_id=None, domain_id="juridique",
            input_context={}, original_output={},
            original_confidence=conf,
        )
        await al.apply_feedback(lid, choice={}, status=status,
                                  agreement_score=0.8)
    metrics = await al.metrics(window_days=1, domain_id="juridique")
    assert "agreement_rate" in metrics
    assert metrics["total_loops"] >= 3
    assert metrics["accepted_count"] >= 2


async def test_history_returns_loops(pool) -> None:
    al = ActiveLearner(pool)
    await al.submit_loop(
        decision_id=None, domain_id="logistique",
        input_context={}, original_output={},
        original_confidence=0.2,
    )
    history = await al.history(days=1, limit=50)
    assert len(history) >= 1


def test_default_threshold() -> None:
    assert DEFAULT_CONFIDENCE_THRESHOLD == 0.7


async def test_submit_generates_default_proposals(pool) -> None:
    al = ActiveLearner(pool)
    loop_id = await al.submit_loop(
        decision_id=None, domain_id="fiscal_dz",
        input_context={}, original_output={"value": 42},
        original_confidence=0.3,
    )
    pending = await al.list_pending(domain_id="fiscal_dz")
    target = next(lp for lp in pending if lp.id == loop_id)
    assert len(target.proposals) >= 2


async def test_migration_029_tables(pool) -> None:
    async with pool.acquire() as conn:
        for tbl in ("active_learning_loops", "active_learning_metrics"):
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = $1)", tbl,
            )
            assert exists, f"Table {tbl} missing"
