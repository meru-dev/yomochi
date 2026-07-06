import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.insights.ports.ai_insight_client import InsightResponse
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.application.insights.ports.work_unit import InsightWorkUnit
from app.application.insights.use_cases.process_insight import (
    ProcessInsightCommand,
    ProcessInsightUseCase,
)
from app.application.insights.use_cases.request_insight import (
    RequestInsightCommand,
    RequestInsightUseCase,
)
from app.application.transactions.use_cases.create_transaction import (
    CreateTransactionCommand,
    CreateTransactionUseCase,
)
from app.domain.entities.insight import Insight
from app.domain.value_objects.enums import ContextQuality, InsightStatus, Period, Plan
from app.domain.value_objects.ids import InsightId, UserId
from app.main.config.settings import InsightWorkerSettings
from tests.fakes.id_generator import FakeInsightIdGenerator, FakeTransactionIdGenerator
from tests.fakes.repositories import (
    FakeCategoryListReader,
    FakeOutboxRepository,
    FakeTransactionRepository,
)

pytestmark = pytest.mark.asyncio


class _InMemoryInsightRepo:
    def __init__(self) -> None:
        self.by_id: dict[InsightId, Insight] = {}

    async def save(self, insight: Insight) -> None:
        self.by_id[insight.id_] = insight

    async def claim_for_processing(
        self, insight_id: InsightId, user_id: UserId, deadline: datetime
    ) -> Insight:
        from app.application.insights.ports.insight_repository import (
            InsightAlreadyTerminalError,
            InsightNotFoundError,
        )

        insight = self.by_id.get(insight_id)
        if insight is None or insight.user_id != user_id:
            raise InsightNotFoundError(str(insight_id))
        if insight.status != InsightStatus.QUEUED:
            raise InsightAlreadyTerminalError(insight.status)
        insight.mark_processing(deadline)
        return insight

    async def get_by_id(self, insight_id: InsightId, user_id: UserId) -> Insight | None:
        return self.by_id.get(insight_id)

    async def count_created_in_month(self, user_id: UserId, year: int, month: int) -> int:
        return sum(
            1
            for i in self.by_id.values()
            if i.user_id == user_id and i.created_at.year == year and i.created_at.month == month
        )

    async def reap_expired_processing(self, max_retries: int):
        from app.application.insights.ports.insight_repository import ReapResult

        del max_retries
        return ReapResult(requeued=[], exhausted_count=0)


class _FakeMetrics:
    def consumer_idempotency_skip(self, topic: str) -> None: ...
    def consumer_dlq_event(self, topic: str) -> None: ...
    def insight_generation_observed(self, *args, **kwargs) -> None: ...


async def test_full_flow_create_transaction_to_insight_completed() -> None:
    user_id = UserId(uuid.uuid4())

    # ---------- 1. create transactions ----------
    # The transaction-worker Kafka path and the dirty-period subsystem have been
    # removed; CreateTransactionUseCase just persists + audits.
    tx_repo = FakeTransactionRepository()
    outbox = FakeOutboxRepository()
    user_plan_lookup = MagicMock()
    user_plan_lookup.get_plan = AsyncMock(return_value=Plan.FREE)

    class _NoOpQuotaCheck:
        async def check_and_increment(self, *a: object, **kw: object) -> None: ...

    create_tx = CreateTransactionUseCase(
        transaction_repo=tx_repo,
        id_generator=FakeTransactionIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        category_list_reader=FakeCategoryListReader(),
        quota_check=_NoOpQuotaCheck(),  # type: ignore[arg-type]
        audit_log=AsyncMock(),  # type: ignore[arg-type]
    )

    # seed 6 transactions so the insight gating passes (min=5)
    for i in range(6):
        await create_tx(
            CreateTransactionCommand(
                user_id=user_id,
                raw_amount=f"{(i + 1) * 100}.00",
                currency="USD",
                date_=date(2026, 4, 1 + i),
                type_="expense",
            )
        )

    # No outbox events emitted for transactions (consumer removed).
    assert len(outbox.events) == 0

    # ---------- 2. request insight ----------
    insight_repo = _InMemoryInsightRepo()
    tx_reader = AsyncMock()
    tx_reader.count_for_period = AsyncMock(return_value=6)

    request_insight = RequestInsightUseCase(
        insight_repo=insight_repo,
        outbox_repo=outbox,
        transaction_reader=tx_reader,
        id_generator=FakeInsightIdGenerator(),
        user_plan_lookup=user_plan_lookup,
        quota_check=_NoOpQuotaCheck(),  # type: ignore[arg-type]
        settings=InsightWorkerSettings(min_transactions_for_insight=5),
    )
    result = await request_insight(
        RequestInsightCommand(
            user_id=user_id, period=Period.MONTHLY, period_year=2026, period_month=4
        )
    )
    insight_id = InsightId(uuid.UUID(result.insight_id))
    saved_insight = insight_repo.by_id[insight_id]
    assert saved_insight.status == InsightStatus.QUEUED

    # ---------- 3. process insight via UoW factory ----------
    budget_reader = AsyncMock()
    budget_reader.read_month = AsyncMock(
        return_value=[
            BudgetTransactionRow(
                amount=Decimal("100"),
                currency="USD",
                type_="expense",
                category_label="food",
                day_of_month=10,
            )
        ]
    )
    budget_reader.read_history_months = AsyncMock(return_value={})

    uow = InsightWorkUnit(
        insight_repo=insight_repo,
        budget_reader=budget_reader,
    )

    @asynccontextmanager
    async def _scope():
        yield uow

    def factory():
        return _scope()

    ai_client = AsyncMock()
    ai_client.generate = AsyncMock(
        return_value=InsightResponse(
            title="You spent more on food",
            description="...",
            impact_score=7,
            prompt_tokens=200,
            completion_tokens=80,
        )
    )

    process_insight = ProcessInsightUseCase(
        work_unit_factory=factory,
        ai_client=ai_client,
    )
    await process_insight(ProcessInsightCommand(insight_id=str(insight_id), user_id=str(user_id)))

    final_insight = insight_repo.by_id[insight_id]
    assert final_insight.status == InsightStatus.COMPLETED
    # PARTIAL because read_history_months returns {} (no history → no shift detection)
    assert final_insight.context_quality in {ContextQuality.FULL, ContextQuality.PARTIAL}
    assert final_insight.title == "You spent more on food"
