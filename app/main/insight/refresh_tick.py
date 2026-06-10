import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.embedding_pipeline import EmbeddingPipeline
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.outbound.adapters.sqla.alerts.alert_writer import SqlaAlertWriter
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader
from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter
from app.outbound.adapters.sqla.insights.dirty_period_repository import SqlaDirtyPeriodRepository

logger = structlog.get_logger(__name__)


async def refresh_one_dirty_period(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    detector: BehavioralShiftDetector,
) -> bool:
    """Claim one dirty period and refresh its chunks inside the same TX.

    The session is committed on success, rolled back on any exception (which
    is re-raised). Multiple workers / pollers are safe to call this concurrently
    via `SELECT ... FOR UPDATE SKIP LOCKED` inside `pop_dirty`.
    """
    async with session_factory.begin() as session:
        dirty_repo = SqlaDirtyPeriodRepository(session)
        periods = await dirty_repo.pop_dirty(limit=1)
        if not periods:
            return False
        period = periods[0]
        pipeline = EmbeddingPipeline(
            budget_reader=SqlaBudgetSummaryReader(session),
            chunk_writer=SqlaChunkWriter(session),
            embedder=embedder,
            shift_detector=detector,
            alert_writer=SqlaAlertWriter(session),
        )
        await pipeline.refresh(period.user_id, period.year, period.month)
        logger.info(
            "embedding_refresh_period",
            user_id=str(period.user_id),
            year=period.year,
            month=period.month,
        )
        return True
