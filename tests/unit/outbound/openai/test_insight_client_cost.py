from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.insights.ports.ai_insight_client import InsightRequest
from app.domain.value_objects.enums import Period
from app.outbound.adapters.openai.insight_client import OpenAIInsightClient
from app.outbound.adapters.openai.pricing import estimate_cost
from app.outbound.observability.prometheus import openai_cost_usd_total

pytestmark = pytest.mark.asyncio


def _make_mock_client(prompt_tokens: int, completion_tokens: int) -> MagicMock:
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = prompt_tokens
    mock_usage.completion_tokens = completion_tokens

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
