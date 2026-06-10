import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.common.ports.text_embedder import TextEmbedder
from app.application.insights.portrait_pipeline import PortraitPipeline
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.budget_summary_reader import SqlaBudgetSummaryReader
from app.outbound.adapters.sqla.insights.chunk_writer import SqlaChunkWriter
from app.outbound.adapters.sqla.insights.portrait_queue import SqlaPortraitQueue

logger = structlog.get_logger(__name__)


async def pop_dirty_batch(
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int,
) -> list[UserId]:
    """Claim a batch of dirty user_ids from portrait_queue."""
    async with session_factory.begin() as session:
        return await SqlaPortraitQueue(session).pop_dirty(limit=batch_size)


async def refresh_one_portrait_user(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    user_id: UserId,
) -> None:
    """Refresh a single user's portrait inside a dedicated TX.

    Re-raises on any failure. The session is committed on success, rolled back
    on exception. The caller is responsible for re-marking dirty.
    """
    async with session_factory.begin() as session:
        pipeline = PortraitPipeline(
            budget_reader=SqlaBudgetSummaryReader(session),
            chunk_writer=SqlaChunkWriter(session),
            embedder=embedder,
        )
        await pipeline.refresh(user_id)
        logger.info("portrait_refresh_user", user_id=str(user_id))


async def requeue_dirty(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: UserId,
) -> None:
    """Re-mark a user dirty after a failed refresh. Best-effort: swallow errors."""
    try:
        async with session_factory.begin() as session:
            await SqlaPortraitQueue(session).mark_dirty(user_id)
    except Exception:
        logger.exception("portrait_requeue_error", user_id=str(user_id))
