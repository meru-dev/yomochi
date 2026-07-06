"""Unit tests for StreamInsightUseCase — status-push watcher (no LLM tokens)."""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.application.insights.ports.work_unit import InsightWorkUnit
from app.application.insights.use_cases.get_insight import InsightNotFoundError
from app.application.insights.use_cases.stream_insight import StreamInsightUseCase
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import InsightStatus, Period
from app.domain.value_objects.ids import InsightId, UserId

pytestmark = pytest.mark.asyncio


def _insight(user_id: UserId, insight_id: InsightId, status: InsightStatus) -> Insight:
    return Insight(
        id_=insight_id,
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=4,
        status=status,
        context_quality=None,
        title="Test" if status == InsightStatus.COMPLETED else None,
        description="Desc" if status == InsightStatus.COMPLETED else None,
        impact_score=7 if status == InsightStatus.COMPLETED else None,
        generated_at=datetime(2026, 4, 1, tzinfo=UTC)
        if status == InsightStatus.COMPLETED
        else None,
        error_message="boom" if status == InsightStatus.FAILED else None,
        created_at=datetime(2026, 4, 1, tzinfo=UTC),
    )


def _factory_returning(sequence: list[Insight | None]):
    """Build a fake InsightWorkUnitFactory whose repo.get_by_id returns the
    next scripted value on each successive call."""
    insight_repo = AsyncMock()
    insight_repo.get_by_id = AsyncMock(side_effect=list(sequence))
    budget_reader = AsyncMock()
    uow = InsightWorkUnit(insight_repo=insight_repo, budget_reader=budget_reader)

    @asynccontextmanager
    async def _scope():
        yield uow

    def factory():
        return _scope()

    return factory, insight_repo


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.application.insights.use_cases.stream_insight.asyncio.sleep",
        AsyncMock(return_value=None),
    )


async def test_yields_initial_then_only_on_change_until_completed() -> None:
    uid, iid = UserId(uuid.uuid4()), InsightId(uuid.uuid4())
    factory, _ = _factory_returning(
        [
            _insight(uid, iid, InsightStatus.PROCESSING),  # initial
            _insight(uid, iid, InsightStatus.PROCESSING),  # no change -> not yielded
            _insight(uid, iid, InsightStatus.COMPLETED),  # change -> yielded, terminal
        ]
    )
    uc = StreamInsightUseCase(factory, poll_interval_seconds=0.0, max_polls=10)

    statuses = [ins.status async for ins in uc(iid, uid)]

    assert statuses == [InsightStatus.PROCESSING, InsightStatus.COMPLETED]


async def test_terminal_on_first_read_returns_after_single_yield() -> None:
    uid, iid = UserId(uuid.uuid4()), InsightId(uuid.uuid4())
    factory, repo = _factory_returning([_insight(uid, iid, InsightStatus.COMPLETED)])
    uc = StreamInsightUseCase(factory, poll_interval_seconds=0.0, max_polls=10)

    results = [ins async for ins in uc(iid, uid)]

    assert [r.status for r in results] == [InsightStatus.COMPLETED]
    repo.get_by_id.assert_called_once()


async def test_failed_sequence_ends_correctly() -> None:
    uid, iid = UserId(uuid.uuid4()), InsightId(uuid.uuid4())
    factory, _ = _factory_returning(
        [
            _insight(uid, iid, InsightStatus.QUEUED),
            _insight(uid, iid, InsightStatus.PROCESSING),
            _insight(uid, iid, InsightStatus.FAILED),
        ]
    )
    uc = StreamInsightUseCase(factory, poll_interval_seconds=0.0, max_polls=10)

    results = [ins async for ins in uc(iid, uid)]

    assert [r.status for r in results] == [
        InsightStatus.QUEUED,
        InsightStatus.PROCESSING,
        InsightStatus.FAILED,
    ]
    assert results[-1].error_message == "boom"


async def test_not_found_first_read_raises() -> None:
    uid, iid = UserId(uuid.uuid4()), InsightId(uuid.uuid4())
    factory, _ = _factory_returning([None])
    uc = StreamInsightUseCase(factory, poll_interval_seconds=0.0, max_polls=10)

    with pytest.raises(InsightNotFoundError):
        [ins async for ins in uc(iid, uid)]


async def test_max_polls_cap_returns_without_raising() -> None:
    uid, iid = UserId(uuid.uuid4()), InsightId(uuid.uuid4())
    # Always PROCESSING, never terminal. 1 initial + max_polls reads.
    factory, repo = _factory_returning(
        [_insight(uid, iid, InsightStatus.PROCESSING) for _ in range(4)]
    )
    uc = StreamInsightUseCase(factory, poll_interval_seconds=0.0, max_polls=3)

    results = [ins async for ins in uc(iid, uid)]

    # Only the initial snapshot is yielded; status never changes -> no more yields.
    assert [r.status for r in results] == [InsightStatus.PROCESSING]
    # 1 initial read + 3 poll reads.
    assert repo.get_by_id.call_count == 4
