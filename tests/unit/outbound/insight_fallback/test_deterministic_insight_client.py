import pytest

from app.application.insights.ports.ai_insight_client import InsightRequest
from app.application.insights.ports.insight_context import InsightContextChunk
from app.domain.value_objects.enums import Period
from app.outbound.adapters.insight_fallback import DeterministicInsightClient

pytestmark = pytest.mark.asyncio


def _chunk(chunk_type: str, content: str) -> InsightContextChunk:
    return InsightContextChunk(
        content=content,
        chunk_type=chunk_type,
        period_label="March 2026",
        metadata={},
    )


def _request(chunks: list[InsightContextChunk]) -> InsightRequest:
    return InsightRequest(
        period=Period.MONTHLY,
        period_year=2026,
        period_month=3,
        chunks=chunks,
    )


async def test_formats_summary_chunks_into_insight() -> None:
    client = DeterministicInsightClient()
    resp = await client.generate(_request([_chunk("monthly_summary", "You spent 1000 on cafes.")]))

    assert resp.title == "Your March 2026 summary"
    assert "temporarily unavailable" in resp.description
    assert "You spent 1000 on cafes." in resp.description
    # No LLM call → no token spend.
    assert resp.prompt_tokens == 0
    assert resp.completion_tokens == 0
    assert resp.impact_score == 5


async def test_shift_chunk_raises_impact_and_is_included() -> None:
    client = DeterministicInsightClient()
    resp = await client.generate(
        _request(
            [
                _chunk("monthly_summary", "Summary text."),
                _chunk("behavioral_shift", "Cafe spending doubled."),
            ]
        )
    )

    assert "Cafe spending doubled." in resp.description
    assert resp.impact_score == 6


async def test_empty_chunks_still_returns_usable_insight() -> None:
    client = DeterministicInsightClient()
    resp = await client.generate(_request([]))

    assert resp.title == "Your March 2026 summary"
    assert "No detailed breakdown" in resp.description
    assert 1 <= resp.impact_score <= 10


async def test_weekly_period_label() -> None:
    client = DeterministicInsightClient()
    req = InsightRequest(period=Period.WEEKLY, period_year=2026, period_month=12, chunks=[])
    resp = await client.generate(req)

    assert resp.title == "Your Week 12, 2026 summary"
