"""Requeue quarantined (FAILED) outbox rows back to PENDING for replay."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.domain.value_objects.enums import OutboxStatus
from app.outbound.adapters.sqla.common.outbox_admin import SqlaOutboxAdmin
from app.outbound.persistence_sqla.mappings.all import map_tables
from app.outbound.persistence_sqla.mappings.outbox_event import outbox_events

pytestmark = pytest.mark.asyncio


async def _make_factory(db_url: str) -> async_sessionmaker[AsyncSession]:
    map_tables()
    engine = create_async_engine(db_url)
    return async_sessionmaker(engine, autoflush=False, expire_on_commit=False)


async def _insert_failed(
    session: AsyncSession,
    *,
    event_type: str = "InsightRequested",
    retry_count: int = 5,
    failed_at: datetime | None = None,
) -> uuid.UUID:
    row_id = uuid.uuid4()
    await session.execute(
        sa.insert(outbox_events).values(
            id=row_id,
            event_type=event_type,
            aggregate_id=str(uuid.uuid4()),
            payload={},
            status=OutboxStatus.FAILED,
            occurred_at=datetime.now(UTC),
            user_id=None,
            retry_count=retry_count,
            last_error="boom",
            failed_at=failed_at or datetime.now(UTC),
        )
    )
    return row_id


async def _status(session: AsyncSession, row_id: uuid.UUID) -> tuple[str, int, str | None]:
    res = await session.execute(
        sa.select(
            outbox_events.c.status, outbox_events.c.retry_count, outbox_events.c.last_error
        ).where(outbox_events.c.id == row_id)
    )
    return res.one()


async def test_requeue_flips_failed_to_pending_and_resets(pg_url: str) -> None:
    factory = await _make_factory(pg_url)
    async with factory.begin() as session:
        row_id = await _insert_failed(session)

    async with factory.begin() as session:
        admin = SqlaOutboxAdmin(session)
        affected = await admin.requeue_failed(ids=[row_id])

    assert affected == [row_id]
    async with factory() as session:
        status, retry_count, last_error = await _status(session, row_id)
    assert status == OutboxStatus.PENDING
    assert retry_count == 0
    assert last_error is None


async def test_dry_run_does_not_mutate(pg_url: str) -> None:
    factory = await _make_factory(pg_url)
    async with factory.begin() as session:
        row_id = await _insert_failed(session)

    async with factory() as session:
        admin = SqlaOutboxAdmin(session)
        affected = await admin.requeue_failed(ids=[row_id], dry_run=True)

    assert affected == [row_id]
    async with factory() as session:
        status, retry_count, _ = await _status(session, row_id)
    assert status == OutboxStatus.FAILED  # untouched
    assert retry_count == 5


async def test_event_type_filter_and_min_age(pg_url: str) -> None:
    factory = await _make_factory(pg_url)
    old = datetime.now(UTC) - timedelta(minutes=30)
    recent = datetime.now(UTC)
    async with factory.begin() as session:
        old_insight = await _insert_failed(session, event_type="InsightRequested", failed_at=old)
        recent_insight = await _insert_failed(
            session, event_type="InsightRequested", failed_at=recent
        )
        other = await _insert_failed(session, event_type="SomethingElse", failed_at=old)

    # Only InsightRequested rows that failed > 10 min ago → just `old_insight`.
    async with factory.begin() as session:
        admin = SqlaOutboxAdmin(session)
        affected = await admin.requeue_failed(
            event_type="InsightRequested",
            failed_before=datetime.now(UTC) - timedelta(minutes=10),
        )

    assert affected == [old_insight]
    async with factory() as session:
        assert (await _status(session, old_insight))[0] == OutboxStatus.PENDING
        assert (await _status(session, recent_insight))[0] == OutboxStatus.FAILED
        assert (await _status(session, other))[0] == OutboxStatus.FAILED
