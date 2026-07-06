import time
from dataclasses import dataclass
from uuid import UUID

import structlog
from opentelemetry import trace

from app.application.insights.config import InsightWorkerConfig
from app.application.insights.ports.ai_insight_client import AIInsightClient, InsightRequest
from app.application.insights.ports.insight_repository import (
    InsightAlreadyTerminalError,
    InsightNotFoundError,
)
from app.application.insights.ports.work_unit import InsightWorkUnitFactory
from app.application.insights.use_cases._process_insight_steps import (
    AssembledContext,
    ClaimedInsight,
    build_insight_context,
    claim_insight,
    complete_insight,
    record_failure,
)
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.value_objects.enums import ContextQuality, InsightStatus
from app.domain.value_objects.ids import InsightId, UserId

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True, slots=True)
class ProcessInsightCommand:
    insight_id: str
    user_id: str


@dataclass(frozen=True, slots=True)
class ProcessInsightResult:
    context_quality: ContextQuality
    elapsed_seconds: float
    terminal_skip: bool = False


# Re-export for backwards compatibility with consumers / tests.
__all__ = [
    "InsightAlreadyTerminalError",
    "InsightNotFoundError",
    "ProcessInsightCommand",
    "ProcessInsightResult",
    "ProcessInsightUseCase",
]


class ProcessInsightUseCase:
    def __init__(
        self,
        work_unit_factory: InsightWorkUnitFactory,
        ai_client: AIInsightClient,
        shift_detector: BehavioralShiftDetector | None = None,
        config: InsightWorkerConfig | None = None,
    ) -> None:
        self._uow_factory = work_unit_factory
        self._ai_client = ai_client
        self._shift_detector = shift_detector or BehavioralShiftDetector()
        self._config = config or InsightWorkerConfig()

    async def __call__(self, command: ProcessInsightCommand) -> ProcessInsightResult:
        insight_id = InsightId(UUID(command.insight_id))
        user_id = UserId(UUID(command.user_id))

        try:
            claimed: ClaimedInsight = await claim_insight(
                self._uow_factory,
                insight_id,
                user_id,
                lease_minutes=self._config.reaper_lease_minutes,
            )
        except InsightAlreadyTerminalError as exc:
            logger.info(
                "process_insight_terminal_skip",
                insight_id=command.insight_id,
                status=exc.status.value,
            )
            quality = (
                ContextQuality.NONE if exc.status == InsightStatus.FAILED else ContextQuality.FULL
            )
            return ProcessInsightResult(
                context_quality=quality,
                elapsed_seconds=0.0,
                terminal_skip=True,
            )

        start = time.perf_counter()
        try:
            ctx: AssembledContext = await build_insight_context(
                self._uow_factory,
                self._shift_detector,
                user_id=user_id,
                period_year=claimed.period_year,
                period_month=claimed.period_month,
            )

            if ctx.quality == ContextQuality.NONE:
                elapsed = time.perf_counter() - start
                logger.warning("process_insight_no_chunks", insight_id=command.insight_id)
                await record_failure(
                    self._uow_factory,
                    insight_id=insight_id,
                    user_id=user_id,
                    error="No transaction data found for this period",
                )
                return ProcessInsightResult(context_quality=ctx.quality, elapsed_seconds=elapsed)

            with tracer.start_as_current_span("ai_completion"):
                ai_response = await self._ai_client.generate(
                    InsightRequest(
                        period=claimed.period,
                        period_year=claimed.period_year,
                        period_month=claimed.period_month,
                        chunks=ctx.chunks,
                        cache_key=str(user_id),
                    )
                )

            await complete_insight(
                self._uow_factory,
                insight_id=insight_id,
                user_id=user_id,
                ai_response=ai_response,
                context_quality=ctx.quality,
                period_year=claimed.period_year,
                period_month=claimed.period_month,
            )

            elapsed = time.perf_counter() - start
            return ProcessInsightResult(context_quality=ctx.quality, elapsed_seconds=elapsed)

        except Exception as exc:
            elapsed = time.perf_counter() - start
            logger.error(
                "process_insight_failed",
                insight_id=command.insight_id,
                error=str(exc),
                elapsed_seconds=elapsed,
                exc_info=True,
            )
            await record_failure(
                self._uow_factory,
                insight_id=insight_id,
                user_id=user_id,
                error=str(exc),
            )
            raise
