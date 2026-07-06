import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.insights.use_cases.detect_shift_alerts import DetectShiftAlertsUseCase
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.alerts.alert_writer import SqlaAlertWriter
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader

logger = structlog.get_logger(__name__)


async def detect_shift_alerts_for_period(
    session_factory: async_sessionmaker[AsyncSession],
    detector: BehavioralShiftDetector,
    user_id: UserId,
    year: int,
    month: int,
) -> None:
    """Run deterministic shift detection for one (user, period) in its own TX.

    One short committed transaction per (user, period). No OpenAI/embedder is
    involved. Idempotent writes (`SqlaAlertWriter` uses ON CONFLICT DO NOTHING)
    make repeated runs safe.
    """
    async with session_factory.begin() as session:
        use_case = DetectShiftAlertsUseCase(
            budget_reader=SqlaBudgetSummaryReader(session),
            alert_writer=SqlaAlertWriter(session),
            detector=detector,
        )
        await use_case(user_id, year, month)
        logger.debug(
            "shift_alert_period_checked",
            user_id=str(user_id),
            year=year,
            month=month,
        )
