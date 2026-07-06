from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.insights.ports.ai_insight_client import InsightRequest
from app.domain.value_objects.enums import Period
from app.outbound.adapters.openai.insight_client import OpenAIInsightClient
from app.outbound.adapters.openai.pricing import estimate_cost
from app.outbound.observability.prometheus import (
    openai_cached_tokens_total,
    openai_cost_usd_total,
)

pytestmark = pytest.mark.asyncio


def _make_mock_client(
    prompt_tokens: int, completion_tokens: int, cached_tokens: int | None = None
) -> MagicMock:
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = prompt_tokens
    mock_usage.completion_tokens = completion_tokens
    # Real OpenAI usage exposes prompt_tokens_details.cached_tokens as an int (or
    # the details object is absent). MagicMock() would leak a truthy mock, so set
    # the attribute explicitly to model the real shape.
    mock_usage.prompt_tokens_details.cached_tokens = cached_tokens

    mock_parsed = MagicMock()
    mock_parsed.title = "Test insight"
    mock_parsed.description = "A test description."
    mock_parsed.impact_score = 5

    mock_message = MagicMock()
    mock_message.parsed = mock_parsed

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.usage = mock_usage
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.beta.chat.completions.parse = AsyncMock(return_value=mock_response)
    return mock_client


async def test_generate_increments_cost_counter() -> None:
    prompt_tokens = 800
    completion_tokens = 300
    model = "gpt-4o-mini"

    mock_openai_client = _make_mock_client(prompt_tokens, completion_tokens)

    async def fake_call(*, endpoint: str, fn: object, timeout: float | None = None) -> object:
        return await fn(mock_openai_client)  # type: ignore[operator]

    mock_gateway = MagicMock()
    mock_gateway.call = fake_call

    client = OpenAIInsightClient(
        gateway=mock_gateway,
        model=model,
        read_timeout_seconds=30.0,
    )

    counter = openai_cost_usd_total.labels(endpoint="chat", model=model)
    before = counter._value.get()  # type: ignore[attr-defined]

    request = InsightRequest(
        period=Period.MONTHLY,
        period_year=2026,
        period_month=3,
        chunks=[],
    )
    await client.generate(request)

    after = counter._value.get()  # type: ignore[attr-defined]
    expected = estimate_cost(
        model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    assert abs(after - before - expected) < 1e-12


def _make_gateway(mock_openai_client: MagicMock) -> MagicMock:
    async def fake_call(*, endpoint: str, fn: object, timeout: float | None = None) -> object:
        return await fn(mock_openai_client)  # type: ignore[operator]

    gateway = MagicMock()
    gateway.call = fake_call
    return gateway


async def test_generate_records_cached_tokens_and_discounts_cost() -> None:
    """Cached prompt tokens increment the cache counter and discount cost."""
    prompt_tokens, completion_tokens, cached_tokens = 1200, 300, 1024
    model = "gpt-4o-mini"

    mock_openai_client = _make_mock_client(prompt_tokens, completion_tokens, cached_tokens)
    client = OpenAIInsightClient(
        gateway=_make_gateway(mock_openai_client), model=model, read_timeout_seconds=30.0
    )

    cached_counter = openai_cached_tokens_total.labels(endpoint="chat", model=model)
    cost_counter = openai_cost_usd_total.labels(endpoint="chat", model=model)
    cached_before = cached_counter._value.get()  # type: ignore[attr-defined]
    cost_before = cost_counter._value.get()  # type: ignore[attr-defined]

    request = InsightRequest(period=Period.MONTHLY, period_year=2026, period_month=3, chunks=[])
    await client.generate(request)

    assert cached_counter._value.get() - cached_before == cached_tokens  # type: ignore[attr-defined]
    # Cost reflects the 50% discount on the cached subset of prompt tokens.
    expected = estimate_cost(
        model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
    )
    discounted = estimate_cost(
        model, prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
    )
    assert expected < discounted  # discount actually applied
    assert abs(cost_counter._value.get() - cost_before - expected) < 1e-12  # type: ignore[attr-defined]


async def test_generate_forwards_prompt_cache_key() -> None:
    """Prompt_cache_key is passed through to the OpenAI parse call."""
    mock_openai_client = _make_mock_client(100, 10)
    parse_mock = mock_openai_client.beta.chat.completions.parse
    client = OpenAIInsightClient(
        gateway=_make_gateway(mock_openai_client), model="gpt-4o-mini", read_timeout_seconds=30.0
    )

    request = InsightRequest(
        period=Period.MONTHLY,
        period_year=2026,
        period_month=3,
        chunks=[],
        cache_key="user-123",
    )
    await client.generate(request)

    assert parse_mock.await_args.kwargs["prompt_cache_key"] == "user-123"
