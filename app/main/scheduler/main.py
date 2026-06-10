import asyncio
from datetime import UTC, date, datetime

import sqlalchemy as sa
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.alerts.ports.alert_repository import AlertRepository
from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.insights.ports.dirty_period_repository import DirtyPeriodRepository
from app.application.insights.ports.insight_repository import InsightRepository
from app.application.insights.ports.portrait_queue import PortraitQueue
from app.application.recurring.use_cases.fire_due_rules import FireDueRulesUseCase
from app.domain.value_objects.ids import UserId
from app.main.config.loader import (
    load_database_settings,
    load_observability_settings,
    load_openai_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    InsightWorkerSettings,
    OpenAISettings,
)
from app.main.ioc.worker_providers import SchedulerProvider, WorkerInfraProvider
from app.main.logging import configure_logging
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)

_ALERT_RETENTION_DAYS = 90


def _prev_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


async def fire_due_rules_job(container: AsyncContainer) -> None:
    async with container() as request_container:
        use_case = await request_container.get(FireDueRulesUseCase)
        today = datetime.now(UTC).date()
        logger.info("scheduler_firing_due_rules", date=today.isoformat())
        await use_case(today=today)
        logger.info("scheduler_done")


async def mark_dirty_prev_month_job(container: AsyncContainer) -> None:
    today = datetime.now(UTC).date()
    year, month = _prev_month(today)

    async with container() as request_container:
        # Raw SQL: iterating all user ids is a one-off task that does not warrant a port.
        # Use the table reflected on the global metadata rather than importing the
        # mapping module (kept lightweight).
        session = await request_container.get(AsyncSession)
        rows = await session.execute(sa.text("SELECT id FROM users"))
        user_ids = list(rows.scalars().all())

        dirty_repo = await request_container.get(DirtyPeriodRepository)
        for uid in user_ids:
            await dirty_repo.mark_dirty(UserId(uid), year, month)

    logger.info("marked_dirty_prev_month", year=year, month=month, user_count=len(user_ids))


async def purge_old_alerts_job(container: AsyncContainer) -> None:
    async with container() as request_container:
        alert_repo = await request_container.get(AlertRepository)
        deleted = await alert_repo.purge_older_than(_ALERT_RETENTION_DAYS)
    logger.info("alerts_purged", deleted_count=deleted, retention_days=_ALERT_RETENTION_DAYS)


async def mark_portrait_dirty_job(container: AsyncContainer) -> None:
    async with container() as request_container:
        portrait_queue = await request_container.get(PortraitQueue)
        count = await portrait_queue.mark_all_dirty()
    logger.info("portrait_queue_marked_all", user_count=count)


async def _reaper_tick(
    insight_repo: InsightRepository,
    outbox_repo: OutboxRepository,
    max_retries: int,
) -> None:
    """Recover orphaned PROCESSING insights.

    Delegates status-transition SQL to InsightRepository.reap_expired_processing.
    Owns only the cross-context concern: re-emitting InsightRequested via outbox
    for requeued rows.
    """
    result = await insight_repo.reap_expired_processing(max_retries)

    now = datetime.now(UTC)
    for reaped in result.requeued:
        await outbox_repo.append(
            OutboxEvent(
                event_type="InsightRequested",
                aggregate_id=str(reaped.insight_id),
                payload={
                    "insight_id": str(reaped.insight_id),
                    "user_id": str(reaped.user_id),
                    "period": reaped.period.value,
                    "period_year": reaped.period_year,
                    "period_month": reaped.period_month,
                },
                occurred_at=now,
                user_id=reaped.user_id.value,
            )
        )

    logger.info(
        "reaper_tick_done",
        requeued=len(result.requeued),
        exhausted=result.exhausted_count,
    )


async def reaper_tick_job(container: AsyncContainer, max_retries: int) -> None:
    async with container() as request_container:
        insight_repo = await request_container.get(InsightRepository)
        outbox_repo = await request_container.get(OutboxRepository)
        await _reaper_tick(insight_repo, outbox_repo, max_retries)


async def run(
    db_settings: DatabaseSettings,
    openai_settings: OpenAISettings,
    insight_settings: InsightWorkerSettings,
) -> None:
    map_tables()

    container = make_async_container(
        WorkerInfraProvider(),
        SchedulerProvider(),
        context={
            DatabaseSettings: db_settings,
            OpenAISettings: openai_settings,
        },
    )

    scheduler = AsyncIOScheduler(timezone=UTC)
    scheduler.add_job(
        fire_due_rules_job,
        "cron",
        hour=0,
        minute=5,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        mark_dirty_prev_month_job,
        "cron",
        day=1,
        hour=1,
        minute=0,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        purge_old_alerts_job,
        "cron",
        day_of_week="sun",
        hour=3,
        minute=30,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        mark_portrait_dirty_job,
        "cron",
        day_of_week="mon",
        hour=3,
        minute=0,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        reaper_tick_job,
        "interval",
        minutes=insight_settings.reaper_interval_minutes,
        kwargs={
            "container": container,
            "max_retries": insight_settings.reaper_max_retries,
        },
        misfire_grace_time=600,
    )
    scheduler.start()
    logger.info("scheduler_worker_started")

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        scheduler.shutdown()
        await container.close()


def main() -> None:
    db_settings = load_database_settings()
    openai_settings = load_openai_settings()
    obs_settings = load_observability_settings()
    insight_settings = InsightWorkerSettings()
    configure_logging(log_format=obs_settings.log_format, debug=False)
    asyncio.run(run(db_settings, openai_settings, insight_settings))


if __name__ == "__main__":
    main()
