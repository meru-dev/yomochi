from datetime import UTC, datetime
from decimal import Decimal

import pytest
import uuid_utils as uuid

from app.domain.entities.insight import Insight
from app.domain.value_objects.budget_summary_snapshot import (
    BudgetSummarySnapshot,
    CurrencyTotals,
)
from app.domain.value_objects.enums import ContextQuality, InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId


def _make_insight(status: InsightStatus = InsightStatus.PENDING) -> Insight:
    return Insight(
        id_=InsightId(uuid.uuid7()),
        user_id=UserId(uuid.uuid7()),
        period=Period.MONTHLY,
        period_year=2025,
        period_month=1,
        status=status,
        context_quality=None,
        title=None,
        description=None,
        impact_score=None,
        generated_at=None,
        error_message=None,
        created_at=datetime(2025, 1, 1, tzinfo=UTC),
    )


def test_mark_queued_from_pending_ok():
    insight = _make_insight(InsightStatus.PENDING)
    insight.mark_queued()
    assert insight.status == InsightStatus.QUEUED


def test_mark_queued_from_wrong_state_raises():
    insight = _make_insight(InsightStatus.QUEUED)
    with pytest.raises(ValueError, match="Cannot queue"):
        insight.mark_queued()


def test_mark_processing_from_queued_ok():
    from datetime import UTC, datetime, timedelta

    insight = _make_insight(InsightStatus.QUEUED)
    deadline = datetime.now(UTC) + timedelta(minutes=15)
    insight.mark_processing(deadline)
    assert insight.status == InsightStatus.PROCESSING
    assert insight.processing_deadline == deadline


def test_mark_completed_requires_processing_state():
    insight = _make_insight(InsightStatus.QUEUED)
    with pytest.raises(ValueError, match="Cannot complete"):
        insight.mark_completed(
            title="t",
            description="d",
            impact_score=5,
            context_quality=ContextQuality.FULL,
            generated_at=datetime.now(UTC),
        )


def test_mark_completed_from_processing_ok():
    insight = _make_insight(InsightStatus.PROCESSING)
    insight.mark_completed(
        title="Spending up",
        description="You spent more this month",
        impact_score=7,
        context_quality=ContextQuality.FULL,
        generated_at=datetime.now(UTC),
    )
    assert insight.status == InsightStatus.COMPLETED
    assert insight.impact_score == 7


def test_mark_completed_rejects_out_of_range_impact_score():
    insight = _make_insight(InsightStatus.PROCESSING)
    with pytest.raises(ValueError, match="1-10"):
        insight.mark_completed(
            title="t",
            description="d",
            impact_score=11,
            context_quality=ContextQuality.FULL,
            generated_at=datetime.now(UTC),
        )


def test_mark_failed_requires_processing_state():
    insight = _make_insight(InsightStatus.COMPLETED)
    with pytest.raises(ValueError, match="Cannot fail"):
        insight.mark_failed("some error")


def test_mark_failed_from_processing_ok():
    insight = _make_insight(InsightStatus.PROCESSING)
    insight.mark_failed("timeout")
    assert insight.status == InsightStatus.FAILED
    assert insight.error_message == "timeout"


def test_mark_completed_persists_budget_summary_snapshot():
    insight = _make_insight(InsightStatus.PROCESSING)
    snapshot = BudgetSummarySnapshot(
        per_currency=(
            CurrencyTotals(
                currency="JPY",
                income=Decimal("0"),
                expense=Decimal("123456"),
                count=7,
            ),
        )
    )
    insight.mark_completed(
        title="t",
        description="d",
        impact_score=5,
        context_quality=ContextQuality.FULL,
        generated_at=datetime.now(UTC),
        budget_summary=snapshot,
    )
    assert insight.budget_summary == snapshot


def test_mark_completed_defaults_budget_summary_to_none():
    insight = _make_insight(InsightStatus.PROCESSING)
    insight.mark_completed(
        title="t",
        description="d",
        impact_score=5,
        context_quality=ContextQuality.FULL,
        generated_at=datetime.now(UTC),
    )
    assert insight.budget_summary is None
