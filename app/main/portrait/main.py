import asyncio
import contextlib
import signal

import structlog
from dishka import make_async_container
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.common.ports.text_embedder import TextEmbedder
from app.domain.value_objects.ids import UserId
from app.main.config.loader import (
    load_database_settings,
    load_observability_settings,
    load_openai_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    ObservabilitySettings,
    OpenAISettings,
)
from app.main.ioc.worker_providers import (
    PortraitAdaptersProvider,
    WorkerInfraProvider,
)
from app.main.logging import configure_logging
from app.main.portrait.refresh_tick import (
    pop_dirty_batch,
    refresh_one_portrait_user,
    requeue_dirty,
)
from app.outbound.observability.otel import configure_otel
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)

_PORTRAIT_INTERVAL_SECONDS = 60
_PORTRAIT_BATCH_SIZE = 10
_PORTRAIT_CONCURRENCY = 3  # concurrent OpenAI embedding calls per batch


async def _refresh_one_portrait_safe(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    uid: UserId,
    sem: asyncio.Semaphore,
) -> None:
    async with sem:
        try:
            await refresh_one_portrait_user(session_factory, embedder, uid)
        except Exception:
            logger.exception("portrait_user_error", user_id=str(uid))
            await requeue_dirty(session_factory, uid)


async def _portrait_refresh_loop(
    session_factory: async_sessionmaker[AsyncSession],
    embedder: TextEmbedder,
    stop: asyncio.Event,
) -> None:
    sem = asyncio.Semaphore(_PORTRAIT_CONCURRENCY)
    while not stop.is_set():
        # Wake immediately on shutdown instead of sleeping out the interval.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=_PORTRAIT_INTERVAL_SECONDS)
        if stop.is_set():
            break
        try:
            user_ids = await pop_dirty_batch(session_factory, _PORTRAIT_BATCH_SIZE)
            if not user_ids:
                continue
            logger.info("portrait_refresh_start", count=len(user_ids))
            results = await asyncio.gather(
                *[
                    _refresh_one_portrait_safe(session_factory, embedder, uid, sem)
                    for uid in user_ids
                ],
                return_exceptions=True,
            )
            # The per-task wrapper catches Exception; this guards BaseException /
            # cancellation leaks that gather would otherwise discard silently.
            for r in results:
                if isinstance(r, BaseException):
                    logger.error("portrait_refresh_task_error", exc_info=r)
            logger.info("portrait_refresh_done", count=len(user_ids))
        except Exception:
            logger.exception("portrait_refresh_loop_error")


async def run(
    db_settings: DatabaseSettings,
    openai_settings: OpenAISettings,
    obs_settings: ObservabilitySettings,
) -> None:
    map_tables()
    configure_logging(log_format=obs_settings.log_format, debug=False)
    configure_otel(
        service_name="yomochi-portrait-worker",
        otlp_endpoint=obs_settings.otel_exporter_otlp_endpoint,
        enabled=obs_settings.otel_enabled,
    )

    container = make_async_container(
        WorkerInfraProvider(),
        PortraitAdaptersProvider(),
        context={
            DatabaseSettings: db_settings,
            OpenAISettings: openai_settings,
        },
    )

    session_factory = await container.get(async_sessionmaker[AsyncSession])
    embedder = await container.get(TextEmbedder)

    if obs_settings.otel_enabled:
        engine = await container.get(AsyncEngine)
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        HTTPXClientInstrumentor().instrument()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    logger.info("portrait_worker_started")
    try:
        await _portrait_refresh_loop(session_factory, embedder, stop)
    finally:
        await container.close()


def main() -> None:
    db_settings = load_database_settings()
    openai_settings = load_openai_settings()
    obs_settings = load_observability_settings()
    asyncio.run(run(db_settings, openai_settings, obs_settings))


if __name__ == "__main__":
    main()
