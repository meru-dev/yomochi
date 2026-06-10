from __future__ import annotations

from tests.evals.categorization.scorer import score_categorization


def test_top_1_hit() -> None:
    result = score_categorization(
        case_id="c1",
        expected="konbini",
        predicted_ranked=["konbini", "food", "shopping"],
        cost_usd=0.0001,
    )
    assert result.passed is True
    assert result.score == 1.0
    assert result.details["rank"] == 1


def test_top_3_hit_but_not_top_1() -> None:
    result = score_categorization(
        case_id="c2",
        expected="konbini",
        predicted_ranked=["food", "shopping", "konbini"],
        cost_usd=0.0001,
    )
    assert result.passed is False  # top-1 metric strict
    assert result.details["rank"] == 3
    assert result.details["in_top_3"] is True


def test_no_hit() -> None:
    result = score_categorization(
        case_id="c3",
        expected="konbini",
        predicted_ranked=["food", "shopping", "transport"],
        cost_usd=0.0001,
    )
    assert result.passed is False
    assert result.details["rank"] is None
    assert result.details["in_top_3"] is False
