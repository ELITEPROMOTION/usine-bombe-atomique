"""Tests du pipeline de validation 9 niveaux."""
import pytest
from app.validation.pipeline import run_pipeline, LEVEL_WEIGHTS


@pytest.mark.asyncio
async def test_pipeline_default_pass():
    result = await run_pipeline(artifacts={})
    assert len(result.levels) == 9
    assert result.verdict == "PASS"
    assert result.global_score == pytest.approx(1.0, rel=1e-6)


def test_level_weights_sum_to_one():
    assert sum(LEVEL_WEIGHTS.values()) == pytest.approx(1.0, rel=1e-9)
