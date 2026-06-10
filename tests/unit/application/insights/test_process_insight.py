import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.application.common.context_quality import assess_quality as _assess_quality
from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.application.insights.ports.chunk_retriever import RetrievedChunk
from app.application.insights.ports.insight_repository import (
    InsightAlreadyTerminalError,
    InsightNotFoundError,
)
from app.application.insights.ports.work_unit import InsightWorkUnit
from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightUseCase,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.budget_summary_snapshot import BudgetSummarySnapshot
from app.domain.value_objects.enums import ContextQuality, InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId


def _queued_insight(user_id: UserId, insight_id: InsightId) -> Insight:
    insight = Insight(
        id_=insight_id,
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=4,
        status=InsightStatus.PENDING,
        context_quality=None,
        title=None,
        description=None,
        impact_score=None,
        generated_at=None,
        error_message=None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )
    insight.mark_queued()
    return insight


def _make_use_case(
    insight: Insight | None,
    chunks: list,
    *,
    claim_raises: Exception | None = None,
    ai_raises: Exception | None = None,
    budget_rows: list[BudgetTransactionRow] | None = None,
    portrait: RetrievedChunk | None = None,
):
    """Build a fake UoW factory + use case.

    The factory yields a fresh dataclass each call so tests can rely on the same
    insight reference being returned from claim and lookups.
    """
    insight_repo = AsyncMock()
    if claim_raises is not None:
        insight_repo.claim_for_processing = AsyncMock(side_effect=claim_raises)
    elif insight is not None:
        # Adapter atomically transitions to PROCESSING.
        async def _claim(_id, _user_id, _deadline):
            insight.status = InsightStatus.PROCESSING
            return insight

        insight_repo.claim_for_processing = AsyncMock(side_effect=_claim)
    else:
        insight_repo.claim_for_processing = AsyncMock(side_effect=InsightNotFoundError("missing"))

    insight_repo.get_by_id = AsyncMock(return_value=insight)
    insight_repo.save = AsyncMock()

    chunk_retriever = AsyncMock()
    chunk_retriever.search = AsyncMock(return_value=chunks)
    chunk_retriever.get_portrait = AsyncMock(return_value=portrait)

    chunk_writer = AsyncMock()
    budget_reader = AsyncMock()
    budget_reader.read_month = AsyncMock(return_value=budget_rows or [])
    budget_reader.read_history_months = AsyncMock(return_value={})

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        chunk_writer=chunk_writer,
        chunk_retriever=chunk_retriever,
        budget_reader=budget_reader,
        alert_writer=AsyncMock(),
        dirty_period_repo=AsyncMock(),
    )

    @asynccontextmanager
    async def _factory_scope():
        yield uow

    def factory():
        return _factory_scope()

    embedder = AsyncMock()
    embedder.embed = AsyncMock(return_value=[0.1] * 1536)

    ai_client = AsyncMock()
    if ai_raises:
        ai_client.generate = AsyncMock(side_effect=ai_raises)
    else:
        ai_client.generate = AsyncMock(
            return_value=InsightResponse(
                title="You spent a lot",
                description="Details here",
                impact_score=6,
                prompt_tokens=100,
                completion_tokens=50,
            )
        )

    uc = ProcessInsightUseCase(
        work_unit_factory=factory,
        embedder=embedder,
        ai_client=ai_client,
    )
    return uc, insight_repo


def _cmd(insight_id: InsightId, user_id: UserId) -> ProcessInsightCommand:
    return ProcessInsightCommand(
        insight_id=str(insight_id),
        user_id=str(user_id),
    )


pytestmark = pytest.mark.asyncio


async def test_marks_insight_completed_on_success() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    chunks = [
        RetrievedChunk(content="c", chunk_type="monthly_summary", period_label="Apr", metadata={}),
        RetrievedChunk(content="c", chunk_type="behavioral_shift", period_label="Apr", metadata={}),
    ]

    uc, repo = _make_use_case(insight, chunks)
    result = await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.COMPLETED
    assert insight.title == "You spent a lot"
    assert insight.impact_score == 6
    assert result.context_quality == ContextQuality.FULL
    assert result.terminal_skip is False
    # Two saves: one inside claim adapter (merge), one for COMPLETED in the save TX.
    assert repo.save.await_count >= 1


async def test_marks_insight_failed_and_reraises_on_ai_error() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    chunks = [
        RetrievedChunk(content="c", chunk_type="monthly_summary", period_label="Apr", metadata={})
    ]
    uc, _ = _make_use_case(insight, chunks=chunks, ai_raises=RuntimeError("openai down"))

    with pytest.raises(RuntimeError, match="openai down"):
        await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.FAILED
    assert insight.error_message is not None
    assert "openai down" in insight.error_message


async def test_raises_not_found_when_insight_missing() -> None:
    user_id = UserId(uuid.uuid4())
    uc, _ = _make_use_case(insight=None, chunks=[])

    with pytest.raises(InsightNotFoundError):
        await uc(_cmd(InsightId(uuid.uuid4()), user_id))


async def test_terminal_skip_when_insight_already_completed() -> None:
    """Re-delivery of an event whose insight is already COMPLETED → no raise, terminal_skip=True."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    uc, _ = _make_use_case(
        insight=None,
        chunks=[],
        claim_raises=InsightAlreadyTerminalError(InsightStatus.COMPLETED),
    )

    result = await uc(_cmd(insight_id, user_id))
    assert result.terminal_skip is True


async def test_terminal_skip_when_insight_already_failed() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    uc, _ = _make_use_case(
        insight=None,
        chunks=[],
        claim_raises=InsightAlreadyTerminalError(InsightStatus.FAILED),
    )

    result = await uc(_cmd(insight_id, user_id))
    assert result.terminal_skip is True
    assert result.context_quality == ContextQuality.NONE


# --- _assess_quality unit tests (unchanged) ---


def test_assess_quality_full_when_monthly_and_shift() -> None:
    chunks = [
        RetrievedChunk(content="", chunk_type="monthly_summary", period_label="", metadata={}),
        RetrievedChunk(content="", chunk_type="behavioral_shift", period_label="", metadata={}),
    ]
    assert _assess_quality(chunks) == ContextQuality.FULL


def test_assess_quality_partial_when_monthly_only() -> None:
    chunks = [
        RetrievedChunk(content="", chunk_type="monthly_summary", period_label="", metadata={})
    ]
    assert _assess_quality(chunks) == ContextQuality.PARTIAL


def test_assess_quality_partial_when_shift_only() -> None:
    chunks = [
        RetrievedChunk(content="", chunk_type="behavioral_shift", period_label="", metadata={})
    ]
    assert _assess_quality(chunks) == ContextQuality.PARTIAL


def test_assess_quality_none_when_no_chunks() -> None:
    assert _assess_quality([]) == ContextQuality.NONE


def test_assess_quality_none_when_portrait_only() -> None:
    """Portrait chunks exist but no monthly_summary or behavioral_shift → NONE.

    The portrait chunk is used for prompt budget pinning, not for quality grading.
    A user whose monthly chunks haven't been refreshed yet gets NONE, not PARTIAL.
    """
    chunks = [
        RetrievedChunk(
            content="spending habits text",
            chunk_type="user_portrait",
            period_label="portrait",
            metadata={},
        )
    ]
    assert _assess_quality(chunks) == ContextQuality.NONE


# --- BudgetSummarySnapshot.aggregate_rows (unchanged) ---


def test_aggregate_rows_returns_none_when_no_rows() -> None:
    assert BudgetSummarySnapshot.aggregate_rows([]) is None


def test_aggregate_rows_aggregates_per_currency_and_type() -> None:
    rows = [
        BudgetTransactionRow(
            amount=Decimal("100"),
            currency="JPY",
            type_="expense",
            category_label="food",
            day_of_month=1,
        ),
        BudgetTransactionRow(
            amount=Decimal("250"),
            currency="JPY",
            type_="expense",
            category_label="food",
            day_of_month=3,
        ),
        BudgetTransactionRow(
            amount=Decimal("5000"),
            currency="JPY",
            type_="income",
            category_label=None,
            day_of_month=25,
        ),
        BudgetTransactionRow(
            amount=Decimal("42.50"),
            currency="USD",
            type_="expense",
            category_label=None,
            day_of_month=2,
        ),
    ]
    snap = BudgetSummarySnapshot.aggregate_rows(rows)
    assert snap is not None
    assert [ct.currency for ct in snap.per_currency] == ["JPY", "USD"]
    jpy = snap.per_currency[0]
    assert jpy.expense == Decimal("350")
    assert jpy.income == Decimal("5000")
    assert jpy.count == 3
    usd = snap.per_currency[1]
    assert usd.expense == Decimal("42.50")
    assert usd.income == Decimal("0")
    assert usd.count == 1


async def test_process_insight_persists_budget_snapshot_on_completion() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    chunks = [
        RetrievedChunk(content="c", chunk_type="monthly_summary", period_label="Apr", metadata={}),
    ]
    budget_rows = [
        BudgetTransactionRow(
            amount=Decimal("123"),
            currency="JPY",
            type_="expense",
            category_label=None,
            day_of_month=10,
        ),
    ]

    uc, _ = _make_use_case(insight, chunks, budget_rows=budget_rows)
    await uc(_cmd(insight_id, user_id))

    assert insight.budget_summary is not None
    assert len(insight.budget_summary.per_currency) == 1
    assert insight.budget_summary.per_currency[0].currency == "JPY"
    assert insight.budget_summary.per_currency[0].expense == Decimal("123")


async def test_process_insight_leaves_snapshot_none_when_no_rows() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)
    chunks = [
        RetrievedChunk(content="c", chunk_type="monthly_summary", period_label="Apr", metadata={}),
    ]

    uc, _ = _make_use_case(insight, chunks, budget_rows=[])
    await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.COMPLETED
    assert insight.budget_summary is None


async def test_portrait_chunk_appended_when_present() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    monthly_chunk = RetrievedChunk(
        content="monthly",
        chunk_type="monthly_summary",
        period_label="Apr",
        metadata={},
    )
    portrait_chunk = RetrievedChunk(
        content="portrait",
        chunk_type="user_portrait",
        period_label="portrait",
        metadata={},
    )

    uc, _ = _make_use_case(insight, [monthly_chunk], portrait=portrait_chunk)
    await uc(_cmd(insight_id, user_id))

    # Verify AI was called with the portrait chunk in the request payload.
    # The ai_client is on the use case, not the UoW.
    sent_chunks = uc._ai_client.generate.call_args[0][0].chunks
    assert portrait_chunk in sent_chunks
    assert monthly_chunk in sent_chunks
