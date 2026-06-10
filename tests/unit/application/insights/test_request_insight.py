import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.insights.use_cases.request_insight import (
    InsufficientTransactionsError,
    RequestInsightCommand,
    RequestInsightUseCase,
)
from app.domain.value_objects.enums import InsightStatus, Period, Plan
from app.domain.value_objects.ids import UserId
from app.main.config.settings import InsightWorkerSettings
from tests.fakes.id_generator import FakeInsightIdGenerator
from tests.fakes.repositories import FakeOutboxRepository

pytestmark = pytest.mark.asyncio

MIN_TX = 5
_SETTINGS = InsightWorkerSettings(min_transactions_for_insight=MIN_TX)


def _make_use_case(tx_count: int = MIN_TX) -> tuple[RequestInsightUseCase, FakeOutboxRepository]:
    insight_repo = AsyncMock()
    insight_repo.save = AsyncMock()
    tx_reader = AsyncMock()
    tx_reader.count_for_period = AsyncMock(return_value=tx_count)
    outbox = FakeOutboxRepository()

    user_plan_lookup = MagicMock()
    user_plan_lookup.get_plan = AsyncMock(return_value=Plan.FREE)

    class _NoOpQuotaCheck:
        async def check_and_increment(self, *a: object, **kw: object) -> None: ...

    uc = RequestInsightUseCase(
        insight_repo=insight_repo,
        outbox_repo=outbox,
        transaction_reader=tx_reader,
        id_generator=FakeInsightIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        quota_check=_NoOpQuotaCheck(),  # type: ignore[arg-type]
        settings=_SETTINGS,
    )
    return uc, outbox


def _cmd(user_id: UserId) -> RequestInsightCommand:
    return RequestInsightCommand(
        user_id=user_id,
        period=Period.MONTHLY,
        period_year=2026,
        period_month=4,
    )


async def test_creates_insight_with_queued_status() -> None:
    uc, _ = _make_use_case(tx_count=MIN_TX)
    user_id = UserId(uuid.uuid4())

    result = await uc(_cmd(user_id))

    assert result.insight_id
    uc._insight_repo.save.assert_called_once()
    saved: object = uc._insight_repo.save.call_args[0][0]
    assert saved.status == InsightStatus.QUEUED
    assert saved.user_id == user_id


async def test_emits_insight_requested_outbox_event() -> None:
    uc, outbox = _make_use_case(tx_count=10)
    user_id = UserId(uuid.uuid4())

    result = await uc(_cmd(user_id))

    assert len(outbox.events) == 1
    event = outbox.events[0]
    assert event.event_type == "InsightRequested"
    assert event.payload["insight_id"] == result.insight_id
    assert event.payload["period_year"] == 2026
    assert event.payload["period_month"] == 4


async def test_raises_when_insufficient_transactions() -> None:
    uc, outbox = _make_use_case(tx_count=MIN_TX - 1)

    with pytest.raises(InsufficientTransactionsError):
        await uc(_cmd(UserId(uuid.uuid4())))

    assert len(outbox.events) == 0


async def test_does_not_create_insight_when_below_threshold() -> None:
    uc, _ = _make_use_case(tx_count=0)

    with pytest.raises(InsufficientTransactionsError):
        await uc(_cmd(UserId(uuid.uuid4())))

    uc._insight_repo.save.assert_not_called()
