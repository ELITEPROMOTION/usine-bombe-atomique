"""Tests du pipeline de validation 5 niveaux (V1)."""
import pytest

from app.validation.pipeline import LEVEL_WEIGHTS, run_pipeline


@pytest.mark.asyncio
async def test_pipeline_empty_artifacts_hard_fails():
    result = await run_pipeline(artifacts={})
    assert len(result.levels) == 5
    assert result.verdict == "HARD_FAIL"
    assert result.global_score < 0.5


def test_level_weights_sum_to_one():
    assert sum(LEVEL_WEIGHTS.values()) == pytest.approx(1.0, rel=1e-9)
    assert set(LEVEL_WEIGHTS.keys()) == {1, 2, 3, 4, 5}
