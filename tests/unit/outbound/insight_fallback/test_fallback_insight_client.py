from unittest.mock import AsyncMock

import pytest

from app.application.common.ai_errors import AIUnavailableError, OpenAICallError
from app.application.insights.ports.ai_insight_client import InsightRequest, InsightResponse
from app.domain.value_objects.enums import Period
from app.outbound.adapters.insight_fallback import FallbackAIInsightClient
from app.outbound.observability.prometheus import insight_fallback_total

pytestmark = pytest.mark.asyncio


def _request() -> InsightRequest:
    return InsightRequest(period=Period.MONTHLY, period_year=2026, period_month=3, chunks=[])


def _response(title: str) -> InsightResponse:
    return InsightResponse(
        title=title, description="d", impact_score=5, prompt_tokens=10, completion_tokens=2
    )


async def test_primary_success_does_not_call_fallback() -> None:
    primary = AsyncMock()
    primary.generate.return_value = _response("primary")
    fallback = AsyncMock()
    client = FallbackAIInsightClient(primary=primary, fallback=fallback)

    resp = await client.generate(_request())

    assert resp.title == "primary"
    fallback.generate.assert_not_awaited()


async def test_primary_gateway_error_falls_back_and_records_metric() -> None:
    primary = AsyncMock()
    primary.generate.side_effect = AIUnavailableError("circuit breaker is open")
    fallback = AsyncMock()
    fallback.generate.return_value = _response("fallback")
    client = FallbackAIInsightClient(primary=primary, fallback=fallback)

    before = insight_fallback_total.labels(reason="unavailable")._value.get()  # type: ignore[attr-defined]
    resp = await client.generate(_request())
    after = insight_fallback_total.labels(reason="unavailable")._value.get()  # type: ignore[attr-defined]

    assert resp.title == "fallback"
    fallback.generate.assert_awaited_once()
    assert after - before == 1


async def test_non_gateway_error_propagates_not_masked() -> None:
    """A non-OpenAICallError (e.g. malformed structured output) must surface so it
    lands in the DLQ, not be silently swallowed by degraded mode."""
    primary = AsyncMock()
    primary.generate.side_effect = ValueError("no parsed structured output")
    fallback = AsyncMock()
    client = FallbackAIInsightClient(primary=primary, fallback=fallback)

    with pytest.raises(ValueError, match="no parsed"):
        await client.generate(_request())
    fallback.generate.assert_not_awaited()


async def test_base_gateway_error_uses_error_reason() -> None:
    primary = AsyncMock()
    primary.generate.side_effect = OpenAICallError("weird")
    fallback = AsyncMock()
    fallback.generate.return_value = _response("fallback")
    client = FallbackAIInsightClient(primary=primary, fallback=fallback)

    before = insight_fallback_total.labels(reason="error")._value.get()  # type: ignore[attr-defined]
    await client.generate(_request())
    after = insight_fallback_total.labels(reason="error")._value.get()  # type: ignore[attr-defined]

    assert after - before == 1
