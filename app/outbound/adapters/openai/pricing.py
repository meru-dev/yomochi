from decimal import Decimal

_PROMPT: dict[str, Decimal] = {
    "gpt-4o-mini": Decimal("0.150"),
    "gpt-4o-mini-2024-07-18": Decimal("0.150"),
    "gpt-4o": Decimal("2.500"),
    "gpt-4o-2024-08-06": Decimal("2.500"),
}

_COMPLETION: dict[str, Decimal] = {
    "gpt-4o-mini": Decimal("0.600"),
    "gpt-4o-mini-2024-07-18": Decimal("0.600"),
    "gpt-4o": Decimal("10.000"),
    "gpt-4o-2024-08-06": Decimal("10.000"),
}


# OpenAI bills cached input tokens at 50% of the prompt rate for the gpt-4o
# family (cached tokens are a subset of prompt_tokens, not additive).
_CACHED_DISCOUNT = Decimal("0.5")


def estimate_cost(
    model: str,
    *,
    prompt_tokens: int,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """Return estimated USD cost for a single OpenAI API call.

    ``cached_tokens`` is the subset of ``prompt_tokens`` served from the prompt
    cache; those are discounted to 50% of the prompt rate (gpt-4o family).
    Returns 0.0 for unrecognised models so callers never crash on new models.
    """
    prompt_rate = _PROMPT.get(model)
    completion_rate = _COMPLETION.get(model)
    if prompt_rate is None or completion_rate is None:
        return 0.0
    cached = min(max(cached_tokens, 0), prompt_tokens)
    uncached_prompt = prompt_tokens - cached
    cost = (
        prompt_rate * uncached_prompt
        + prompt_rate * _CACHED_DISCOUNT * cached
        + completion_rate * completion_tokens
    ) / Decimal("1_000_000")
    return float(cost)
