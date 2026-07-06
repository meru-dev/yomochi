import asyncio
import contextlib
import signal
from datetime import UTC, date, datetime

import sqlalchemy as sa
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dishka import AsyncContainer, make_async_container
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.alerts.ports.alert_repository import AlertRepository
from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.outbox_repository import OutboxRepository
from app.application.insights.ports.insight_repository import InsightRepository
from app.application.recurring.use_cases.fire_due_rules import FireDueRulesUseCase
from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.value_objects.enums import OutboxStatus
from app.main.config.loader import (
    load_database_settings,
    load_observability_settings,
    load_openai_settings,
)
from app.main.config.settings import (
    DatabaseSettings,
    InsightWorkerSettings,
    ObservabilitySettings,
    OpenAISettings,
)
from app.main.ioc.worker_providers import SchedulerProvider, WorkerInfraProvider
from app.main.logging import configure_logging
from app.main.scheduler.shift_alert_tick import detect_shift_alerts_for_period
from app.outbound.adapters.sqla.insights.active_user_reader import SqlaActiveUserReader
from app.outbound.observability.otel import configure_otel
from app.outbound.persistence_sqla.mappings.all import map_tables

logger = structlog.get_logger(__name__)

_ALERT_RETENTION_DAYS = 90

# audit_events partition management (B21).
# Number of future monthly partitions to keep pre-created ahead of "now".
_AUDIT_PARTITION_AHEAD_MONTHS = 3
# Detach + drop audit partitions whose month starts more than this many months ago.
_AUDIT_PARTITION_RETENTION_MONTHS = 12

# outbox SENT-row purge (B22).
_OUTBOX_PURGE_AFTER_DAYS = 7
_OUTBOX_PURGE_BATCH_SIZE = 5000

# Idle interval between graceful-shutdown checks in the main loop (B23).
_SHUTDOWN_POLL_SECONDS = 60.0


def _prev_month(today: date) -> tuple[int, int]:
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


def _add_month(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


def _sub_months(year: int, month: int, n: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) - n
    return idx // 12, idx % 12 + 1


async def fire_due_rules_job(container: AsyncContainer) -> None:
    async with container() as request_container:
        use_case = await request_container.get(FireDueRulesUseCase)
        today = datetime.now(UTC).date()
        logger.info("scheduler_firing_due_rules", date=today.isoformat())
        await use_case(today=today)
        logger.info("scheduler_done")


async def detect_shift_alerts_job(container: AsyncContainer) -> None:
    """Deterministic behavioral-shift alerting, off the embedding loop.

    For each recently-active user, run shift detection for BOTH the previous month
    and the current month. The previous month covers late-arriving transactions
    after a month rollover; the current month covers intra-month spikes. The alert
    writer is idempotent (ON CONFLICT DO NOTHING), so the overlap is safe.

    The detector is a pure no-dependency domain object, constructed in the job
    (precedent: this module builds maintenance objects directly rather than via a
    provider). Each (user, period) gets its own short committed TX; no OpenAI here.
    """
    today = datetime.now(UTC).date()
    cur_year, cur_month = today.year, today.month
    prev_year, prev_month = _prev_month(today)
    since = date(prev_year, prev_month, 1)

    detector = BehavioralShiftDetector()
    factory = await container.get(async_sessionmaker[AsyncSession])

    async with factory() as session:
        user_ids = await SqlaActiveUserReader(session).recently_active_user_ids(since)

    for user_id in user_ids:
        await detect_shift_alerts_for_period(factory, detector, user_id, prev_year, prev_month)
        await detect_shift_alerts_for_period(factory, detector, user_id, cur_year, cur_month)

    logger.info(
        "shift_alerts_job_done",
        users_processed=len(user_ids),
        periods=[
            f"{prev_year}-{prev_month:02d}",
            f"{cur_year}-{cur_month:02d}",
        ],
    )


async def manage_audit_partitions_job(container: AsyncContainer) -> None:
    """Pre-create upcoming monthly audit_events partitions and prune old ones (B21).

    Raw SQL via the scheduler session factory: partition DDL is a maintenance
    concern that does not warrant a domain port (precedent in this module).
    """
    today = datetime.now(UTC).date()
    created: list[str] = []
    dropped: list[str] = []

    factory = await container.get(async_sessionmaker[AsyncSession])

    async with factory.begin() as session:
        # Pre-create current month + N future months.
        year, month = today.year, today.month
        for _ in range(_AUDIT_PARTITION_AHEAD_MONTHS + 1):
            nxt_year, nxt_month = _add_month(year, month)
            name = f"audit_events_{year:04d}_{month:02d}"
            await session.execute(
                sa.text(
                    f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF audit_events "
                    f"FOR VALUES FROM ('{year:04d}-{month:02d}-01') "
                    f"TO ('{nxt_year:04d}-{nxt_month:02d}-01')"
                )
            )
            created.append(name)
            year, month = nxt_year, nxt_month

        # Retention: detach + drop partitions older than the retention window.
        cut_year, cut_month = _sub_months(
            today.year, today.month, _AUDIT_PARTITION_RETENTION_MONTHS
        )
        rows = await session.execute(
            sa.text(
                "SELECT inhrelid::regclass::text AS name FROM pg_inherits "
                "WHERE inhparent = 'audit_events'::regclass"
            )
        )
        for (name,) in rows.all():
            if not name.startswith("audit_events_"):
                continue
            suffix = name[len("audit_events_") :]
            parts = suffix.split("_")
            if len(parts) != 2 or not all(p.isdigit() for p in parts):
                continue  # skip audit_events_default and any non-monthly partition
            p_year, p_month = int(parts[0]), int(parts[1])
            if (p_year, p_month) >= (cut_year, cut_month):
                continue
            await session.execute(sa.text(f"ALTER TABLE audit_events DETACH PARTITION {name}"))
            await session.execute(sa.text(f"DROP TABLE {name}"))
            dropped.append(name)

    logger.info("audit_partitions_managed", created=created, dropped=dropped)


async def purge_sent_outbox_job(container: AsyncContainer) -> None:
    """Delete SENT outbox rows older than the retention window, batched (B22)."""
    factory = await container.get(async_sessionmaker[AsyncSession])
    total = 0
    while True:
        async with factory.begin() as session:
            result = await session.execute(
                sa.text(
                    "DELETE FROM outbox_events WHERE id IN ("
                    "  SELECT id FROM outbox_events"
                    "  WHERE status = :status"
                    "    AND occurred_at < now() - make_interval(days => :days)"
                    "  LIMIT :limit"
                    ")"
                ),
                {
                    "status": OutboxStatus.SENT.value,
                    "days": _OUTBOX_PURGE_AFTER_DAYS,
                    "limit": _OUTBOX_PURGE_BATCH_SIZE,
                },
            )
        deleted = int(result.rowcount or 0)  # type: ignore[attr-defined]
        total += deleted
        if deleted < _OUTBOX_PURGE_BATCH_SIZE:
            break
    logger.info("outbox_sent_purged", deleted_count=total, retention_days=_OUTBOX_PURGE_AFTER_DAYS)


async def purge_old_alerts_job(container: AsyncContainer) -> None:
    async with container() as request_container:
        alert_repo = await request_container.get(AlertRepository)
        deleted = await alert_repo.purge_older_than(_ALERT_RETENTION_DAYS)
    logger.info("alerts_purged", deleted_count=deleted, retention_days=_ALERT_RETENTION_DAYS)


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
    obs_settings: ObservabilitySettings,
) -> None:
    map_tables()
    configure_otel(
        service_name="yomochi-scheduler",
        otlp_endpoint=obs_settings.otel_exporter_otlp_endpoint,
        enabled=obs_settings.otel_enabled,
    )

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
        detect_shift_alerts_job,
        "cron",
        hour=2,
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
        reaper_tick_job,
        "interval",
        minutes=insight_settings.reaper_interval_minutes,
        kwargs={
            "container": container,
            "max_retries": insight_settings.reaper_max_retries,
        },
        misfire_grace_time=600,
    )
    scheduler.add_job(
        manage_audit_partitions_job,
        "cron",
        day=1,
        hour=0,
        minute=30,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        purge_sent_outbox_job,
        "cron",
        hour=4,
        minute=0,
        kwargs={"container": container},
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("scheduler_worker_started")

    # Run-on-startup catch-up: ensure upcoming audit partitions exist immediately,
    # don't wait for the monthly cron tick.
    try:
        await manage_audit_partitions_job(container)
    except Exception:
        # Startup catch-up must not crash the worker.
        logger.exception("audit_partition_startup_catchup_failed")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    try:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_SHUTDOWN_POLL_SECONDS)
    finally:
        scheduler.shutdown()
        await container.close()


def main() -> None:
    db_settings = load_database_settings()
    openai_settings = load_openai_settings()
    obs_settings = load_observability_settings()
    insight_settings = InsightWorkerSettings()
    configure_logging(log_format=obs_settings.log_format, debug=False)
    asyncio.run(run(db_settings, openai_settings, insight_settings, obs_settings))


if __name__ == "__main__":
    main()
