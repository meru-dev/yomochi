from __future__ import annotations

import pytest

from app.outbound.adapters.openai.pricing import estimate_cost


def test_gpt4o_mini_prompt_only() -> None:
    cost = estimate_cost("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=0)
    assert abs(cost - 0.150) < 1e-9


def test_gpt4o_mini_completion_only() -> None:
    cost = estimate_cost("gpt-4o-mini", prompt_tokens=0, completion_tokens=1_000_000)
    assert abs(cost - 0.600) < 1e-9


def test_gpt4o_mini_combined() -> None:
    cost = estimate_cost("gpt-4o-mini", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost - 0.750) < 1e-9


def test_gpt4o_combined() -> None:
    cost = estimate_cost("gpt-4o", prompt_tokens=1_000_000, completion_tokens=1_000_000)
    assert abs(cost - 12.500) < 1e-6


def test_unknown_model_returns_zero() -> None:
    cost = estimate_cost("unknown-model-xyz", prompt_tokens=1_000_000, completion_tokens=500_000)
    assert cost == 0.0


def test_zero_tokens_returns_zero() -> None:
    assert estimate_cost("gpt-4o-mini", prompt_tokens=0, completion_tokens=0) == 0.0


@pytest.mark.parametrize("model", ["gpt-4o-mini", "gpt-4o"])
def test_small_token_count_positive(model: str) -> None:
    cost = estimate_cost(model, prompt_tokens=100, completion_tokens=50)
    assert cost >= 0.0


def test_versioned_gpt4o_mini_alias() -> None:
    cost_base = estimate_cost("gpt-4o-mini", prompt_tokens=1_000, completion_tokens=500)
    cost_versioned = estimate_cost(
        "gpt-4o-mini-2024-07-18", prompt_tokens=1_000, completion_tokens=500
    )
    assert abs(cost_base - cost_versioned) < 1e-12
