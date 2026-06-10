from __future__ import annotations

import pytest

from tests.evals.budget import BudgetExceededError, CostEstimate, check_budget, estimate_cost


def test_estimate_cost_for_gpt_4o_mini_chat() -> None:
    cost = estimate_cost(
        model="gpt-4o-mini",
        prompt_tokens=1000,
        completion_tokens=500,
    )
    # $0.150 / 1M prompt + $0.600 / 1M completion
    assert cost == pytest.approx(0.00015 + 0.00030, rel=1e-6)


def test_estimate_cost_for_gpt_4o_judge() -> None:
    cost = estimate_cost(
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=200,
    )
    # $2.50 / 1M prompt + $10.00 / 1M completion
    assert cost == pytest.approx(0.00250 + 0.00200, rel=1e-6)


def test_estimate_cost_for_embedding() -> None:
    cost = estimate_cost(
        model="text-embedding-3-small",
        prompt_tokens=1000,
        completion_tokens=0,
    )
    assert cost == pytest.approx(0.020 / 1_000_000 * 1000, rel=1e-6)


def test_check_budget_passes_under_cap() -> None:
    check_budget(estimated=CostEstimate(usd=0.50), cap_usd=2.00)


def test_check_budget_raises_over_cap() -> None:
    with pytest.raises(BudgetExceededError):
        check_budget(estimated=CostEstimate(usd=2.50), cap_usd=2.00)


def test_estimate_cost_unknown_model_raises_keyerror() -> None:
    with pytest.raises(KeyError):
        estimate_cost(model="gpt-5-ultra", prompt_tokens=100, completion_tokens=0)


def test_check_budget_at_boundary_passes() -> None:
    # Boundary: cost exactly at cap is allowed (strict `>` semantics in check_budget).
    check_budget(estimated=CostEstimate(usd=2.00), cap_usd=2.00)


def test_estimate_cost_zero_tokens_is_zero() -> None:
    assert estimate_cost(model="gpt-4o-mini", prompt_tokens=0, completion_tokens=0) == 0.0
