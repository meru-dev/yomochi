from decimal import Decimal

_PROMPT: dict[str, Decimal] = {
    "gpt-4o-mini": Decimal("0.150"),
    "gpt-4o-mini-2024-07-18": Decimal("0.150"),
    "gpt-4o": Decimal("2.500"),
    "gpt-4o-2024-08-06": Decimal("2.500"),
    "text-embedding-3-small": Decimal("0.020"),
}

_COMPLETION: dict[str, Decimal] = {
    "gpt-4o-mini": Decimal("0.600"),
    "gpt-4o-mini-2024-07-18": Decimal("0.600"),
    "gpt-4o": Decimal("10.000"),
    "gpt-4o-2024-08-06": Decimal("10.000"),
    "text-embedding-3-small": Decimal("0.000"),
}


def estimate_cost(model: str, *, prompt_tokens: int, completion_tokens: int = 0) -> float:
    """Return estimated USD cost for a single OpenAI API call.

    Returns 0.0 for unrecognised models so callers never crash on new models.
    """
    prompt_rate = _PROMPT.get(model)
    completion_rate = _COMPLETION.get(model)
    if prompt_rate is None or completion_rate is None:
        return 0.0
    cost = (prompt_rate * prompt_tokens + completion_rate * completion_tokens) / Decimal(
        "1_000_000"
    )
    return float(cost)
