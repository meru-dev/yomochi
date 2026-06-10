from __future__ import annotations

from dataclasses import dataclass


class BudgetExceededError(RuntimeError):
    pass


PRICING_USD_PER_1M_TOKENS: dict[tuple[str, str], float] = {
    ("gpt-4o-mini", "prompt"): 0.150,
    ("gpt-4o-mini", "completion"): 0.600,
    ("gpt-4o", "prompt"): 2.50,
    ("gpt-4o", "completion"): 10.00,
    ("text-embedding-3-small", "prompt"): 0.020,
    # $0.006/min, normalised to per-token; audio cost computed separately in voice scorer
    ("whisper-1", "prompt"): 0.006 * 1_000_000 / 60,
}


def estimate_cost(*, model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Return USD cost for one call given token counts. Missing model raises KeyError."""
    prompt_rate = PRICING_USD_PER_1M_TOKENS[(model, "prompt")]
    completion_rate = PRICING_USD_PER_1M_TOKENS.get((model, "completion"), 0.0)
    return (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000


@dataclass(frozen=True, slots=True)
class CostEstimate:
    usd: float


def check_budget(*, estimated: CostEstimate, cap_usd: float) -> None:
    if estimated.usd > cap_usd:
        raise BudgetExceededError(
            f"Estimated cost ${estimated.usd:.4f} exceeds cap ${cap_usd:.2f}. "
            "Raise EVALS_BUDGET_USD or reduce evals scope."
        )
