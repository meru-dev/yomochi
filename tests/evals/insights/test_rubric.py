from __future__ import annotations

from tests.evals.insights.rubric import (
    DeterministicChecks,
    check_impact_score_range,
    check_no_fx_summed_total,
    check_no_hallucinated_merchant,
)


def test_impact_score_in_range() -> None:
    assert check_impact_score_range(score=5, allowed=(3, 8)) is True
    assert check_impact_score_range(score=2, allowed=(3, 8)) is False


def test_fx_summed_total_caught() -> None:
    text = "You spent 50000 in JPY and EUR combined this month."
    assert check_no_fx_summed_total(text) is False  # phrase combines currencies

    clean = "You spent ¥45000 on food. In EUR you also paid €120."
    assert check_no_fx_summed_total(clean) is True


def test_hallucinated_merchant_caught() -> None:
    text = "You went to Lawson 5 times and to Bistro Lyon."
    input_merchants = ["Lawson", "FamilyMart"]
    assert check_no_hallucinated_merchant(text, allowed=input_merchants) is False


def test_no_hallucinated_merchant_passes() -> None:
    text = "You went to Lawson 5 times."
    input_merchants = ["Lawson", "FamilyMart"]
    assert check_no_hallucinated_merchant(text, allowed=input_merchants) is True


def test_deterministic_checks_short_circuit() -> None:
    checks = DeterministicChecks(
        impact_score_passed=True,
        no_fx_summed=False,  # one failure means overall fail
        no_hallucinated_merchant=True,
    )
    assert checks.all_passed is False
