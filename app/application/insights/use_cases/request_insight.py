from dataclasses import dataclass
from datetime import UTC, datetime

from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.common.ports.quota_check import QuotaCheck, QuotaResource
from app.application.common.ports.user_plan_lookup import UserPlanLookup
from app.application.insights.config import InsightWorkerConfig
from app.application.insights.ports.insight_repository import InsightRepository
from app.application.insights.ports.transaction_reader import TransactionReader
from app.domain.entities.insight import Insight
from app.domain.ports.id_generator import InsightIdGenerator
from app.domain.value_objects.enums import InsightStatus, Period
from app.domain.value_objects.ids import UserId


class InsufficientTransactionsError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class RequestInsightCommand:
    user_id: UserId
    period: Period
    period_year: int
    period_month: int


@dataclass(frozen=True, slots=True)
class RequestInsightResult:
    insight_id: str


class RequestInsightUseCase:
    def __init__(
        self,
        insight_repo: InsightRepository,
        outbox_repo: OutboxRepository,
        transaction_reader: TransactionReader,
        id_generator: InsightIdGenerator,
        user_plan_lookup: UserPlanLookup,
        quota_check: QuotaCheck,
        settings: InsightWorkerConfig,
    ) -> None:
        self._insight_repo = insight_repo
        self._outbox_repo = outbox_repo
        self._tx_reader = transaction_reader
        self._id_gen = id_generator
        self._user_plan_lookup = user_plan_lookup
        self._quota_check = quota_check
        self._settings = settings

    async def __call__(self, command: RequestInsightCommand) -> RequestInsightResult:
        plan = await self._user_plan_lookup.get_plan(command.user_id)
        await self._quota_check.check_and_increment(command.user_id, QuotaResource.INSIGHTS, plan)

        count = await self._tx_reader.count_for_period(
            command.user_id, command.period_year, command.period_month
        )
        min_tx = self._settings.min_transactions_for_insight
        if count < min_tx:
            raise InsufficientTransactionsError(
                f"User has {count} transactions, minimum is {min_tx}"
            )

        now = datetime.now(UTC)
        insight = Insight(
            id_=self._id_gen(),
            user_id=command.user_id,
            period=command.period,
            period_year=command.period_year,
            period_month=command.period_month,
            status=InsightStatus.PENDING,
            context_quality=None,
            title=None,
            description=None,
            impact_score=None,
            generated_at=None,
            error_message=None,
            created_at=now,
        )
        insight.mark_queued()
        await self._insight_repo.save(insight)
        await self._outbox_repo.append(
            OutboxEvent(
                event_type="InsightRequested",
                aggregate_id=str(insight.id_),
                payload={
                    "insight_id": str(insight.id_),
                    "user_id": str(insight.user_id),
                    "period": insight.period.value,
                    "period_year": insight.period_year,
                    "period_month": insight.period_month,
                },
                occurred_at=now,
                user_id=insight.user_id.value,
            )
        )
        return RequestInsightResult(insight_id=str(insight.id_))
