"""Unit tests for ProcessInsightUseCase — deterministic context path (no RAG)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
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
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
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
    *,
    claim_raises: Exception | None = None,
    ai_raises: Exception | None = None,
    budget_rows: list[BudgetTransactionRow] | None = None,
    history_rows: dict | None = None,
):
    """Build a fake UoW factory + use case (no embedder, no chunk_retriever needed).

    budget_rows are what read_month returns for the insight period.
    history_rows are what read_history_months returns (default: empty dict).
    """
    insight_repo = AsyncMock()
    if claim_raises is not None:
        insight_repo.claim_for_processing = AsyncMock(side_effect=claim_raises)
    elif insight is not None:

        async def _claim(_id, _user_id, _deadline):
            insight.status = InsightStatus.PROCESSING
            return insight

        insight_repo.claim_for_processing = AsyncMock(side_effect=_claim)
    else:
        insight_repo.claim_for_processing = AsyncMock(side_effect=InsightNotFoundError("missing"))

    insight_repo.get_by_id = AsyncMock(return_value=insight)
    insight_repo.save = AsyncMock()

    budget_reader = AsyncMock()
    budget_reader.read_month = AsyncMock(return_value=budget_rows or [])
    budget_reader.read_history_months = AsyncMock(return_value=history_rows or {})

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        budget_reader=budget_reader,
    )

    @asynccontextmanager
    async def _factory_scope():
        yield uow

    def factory():
        return _factory_scope()

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
        ai_client=ai_client,
        shift_detector=BehavioralShiftDetector(),
    )
    return uc, insight_repo, uow


def _cmd(insight_id: InsightId, user_id: UserId) -> ProcessInsightCommand:
    return ProcessInsightCommand(
        insight_id=str(insight_id),
        user_id=str(user_id),
    )


# Minimal rows that pass the period-data check (just expense, 1 row)
def _expense_row(amount: str = "100", currency: str = "JPY") -> BudgetTransactionRow:
    return BudgetTransactionRow(
        amount=Decimal(amount),
        currency=currency,
        type_="expense",
        category_label="food",
        day_of_month=10,
    )


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# New deterministic quality cases
# ---------------------------------------------------------------------------


async def test_none_quality_when_zero_transactions() -> None:
    """Zero rows → NONE quality → insight marked FAILED, AI never called."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    uc, _repo, _ = _make_use_case(insight, budget_rows=[])
    result = await uc(_cmd(insight_id, user_id))

    assert result.context_quality == ContextQuality.NONE
    assert insight.status == InsightStatus.FAILED
    assert insight.error_message is not None
    assert "No transaction data found" in insight.error_message
    # AI must not have been called
    uc._ai_client.generate.assert_not_called()


async def test_partial_quality_when_data_no_shifts() -> None:
    """Rows present but insufficient history for shift detection → PARTIAL quality."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    # history_rows is empty dict → no history → detector returns [] → PARTIAL
    uc, _, _uow = _make_use_case(insight, budget_rows=[_expense_row()], history_rows={})
    result = await uc(_cmd(insight_id, user_id))

    assert result.context_quality == ContextQuality.PARTIAL
    assert insight.status == InsightStatus.COMPLETED
    # AI should have been called with chunks
    uc._ai_client.generate.assert_called_once()
    sent_chunks = uc._ai_client.generate.call_args[0][0].chunks
    chunk_types = {c.chunk_type for c in sent_chunks}
    assert "monthly_summary" in chunk_types
    assert "behavioral_shift" not in chunk_types


async def test_full_quality_when_data_plus_shifts() -> None:
    """Rows present + enough history for shift detection → FULL quality."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    # Seed history with LOW income in prior months, current month has HIGH expenses
    # to trigger an expense_spike shift.
    def _make_row(amount: str, type_: str, currency: str = "JPY") -> BudgetTransactionRow:
        return BudgetTransactionRow(
            amount=Decimal(amount),
            currency=currency,
            type_=type_,
            category_label="food" if type_ == "expense" else None,
            day_of_month=5,
        )

    current_rows = [
        _make_row("10000", "income"),  # large income
        _make_row("9000", "expense"),  # very high expense — will spike vs history
    ]

    # 3 history months with normal (low) expenses → triggers expense_spike
    history_rows = {
        (2026, 1): [_make_row("10000", "income"), _make_row("1000", "expense")],
        (2026, 2): [_make_row("10000", "income"), _make_row("1100", "expense")],
        (2026, 3): [_make_row("10000", "income"), _make_row("1050", "expense")],
    }

    uc, _, _uow = _make_use_case(insight, budget_rows=current_rows, history_rows=history_rows)
    result = await uc(_cmd(insight_id, user_id))

    assert result.context_quality == ContextQuality.FULL
    assert insight.status == InsightStatus.COMPLETED
    sent_chunks = uc._ai_client.generate.call_args[0][0].chunks
    chunk_types = {c.chunk_type for c in sent_chunks}
    assert "monthly_summary" in chunk_types
    assert "behavioral_shift" in chunk_types


# ---------------------------------------------------------------------------
# No embedder/ChunkRetriever interaction on the insight path
# ---------------------------------------------------------------------------


async def test_no_embedder_or_chunk_retriever_called() -> None:
    """The insight path is deterministic: no embedder, no chunk retrieval at all."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    uc, _, uow = _make_use_case(insight, budget_rows=[_expense_row()])
    # Confirm the use case has no _embedder attribute at all
    assert not hasattr(uc, "_embedder")

    result = await uc(_cmd(insight_id, user_id))

    # The insight path must complete successfully (not just "not error")
    assert insight.status == InsightStatus.COMPLETED
    assert result.context_quality in {ContextQuality.FULL, ContextQuality.PARTIAL}

    # The retrieval subsystem is gone: the UoW exposes no chunk retriever at all.
    assert not hasattr(uow, "chunk_retriever")


# ---------------------------------------------------------------------------
# Pre-existing essential behaviours (adapted for new constructor)
# ---------------------------------------------------------------------------


async def test_marks_insight_completed_on_success() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    uc, repo, _ = _make_use_case(insight, budget_rows=[_expense_row()])
    result = await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.COMPLETED
    assert insight.title == "You spent a lot"
    assert insight.impact_score == 6
    assert result.context_quality in {ContextQuality.FULL, ContextQuality.PARTIAL}
    assert result.terminal_skip is False
    assert repo.save.await_count >= 1


async def test_marks_insight_failed_and_reraises_on_ai_error() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    uc, _, _uow = _make_use_case(
        insight, budget_rows=[_expense_row()], ai_raises=RuntimeError("openai down")
    )

    with pytest.raises(RuntimeError, match="openai down"):
        await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.FAILED
    assert insight.error_message is not None
    assert "openai down" in insight.error_message


async def test_raises_not_found_when_insight_missing() -> None:
    user_id = UserId(uuid.uuid4())
    uc, _, _uow = _make_use_case(insight=None)

    with pytest.raises(InsightNotFoundError):
        await uc(_cmd(InsightId(uuid.uuid4()), user_id))


async def test_terminal_skip_when_insight_already_completed() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    uc, _, _uow = _make_use_case(
        insight=None,
        claim_raises=InsightAlreadyTerminalError(InsightStatus.COMPLETED),
    )

    result = await uc(_cmd(insight_id, user_id))
    assert result.terminal_skip is True


async def test_terminal_skip_when_insight_already_failed() -> None:
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    uc, _, _uow = _make_use_case(
        insight=None,
        claim_raises=InsightAlreadyTerminalError(InsightStatus.FAILED),
    )

    result = await uc(_cmd(insight_id, user_id))
    assert result.terminal_skip is True
    assert result.context_quality == ContextQuality.NONE


# ---------------------------------------------------------------------------
# BudgetSummarySnapshot tests (unchanged — still valid)
# ---------------------------------------------------------------------------


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
    budget_rows = [
        BudgetTransactionRow(
            amount=Decimal("123"),
            currency="JPY",
            type_="expense",
            category_label=None,
            day_of_month=10,
        ),
    ]

    uc, _, _uow = _make_use_case(insight, budget_rows=budget_rows)
    await uc(_cmd(insight_id, user_id))

    assert insight.budget_summary is not None
    assert len(insight.budget_summary.per_currency) == 1
    assert insight.budget_summary.per_currency[0].currency == "JPY"
    assert insight.budget_summary.per_currency[0].expense == Decimal("123")


async def test_process_insight_leaves_snapshot_none_when_no_rows() -> None:
    """Zero rows → NONE path (failure) → budget_summary stays None."""
    user_id = UserId(uuid.uuid4())
    insight_id = InsightId(uuid.uuid4())
    insight = _queued_insight(user_id, insight_id)

    uc, _, _uow = _make_use_case(insight, budget_rows=[])
    await uc(_cmd(insight_id, user_id))

    assert insight.status == InsightStatus.FAILED
    assert insight.budget_summary is None
