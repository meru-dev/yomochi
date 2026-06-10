from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.main.scheduler.main import _reaper_tick
from app.outbound.adapters.sqla.common.outbox_repository import SqlaOutboxRepository
from app.outbound.adapters.sqla.insights.insight_repository import SqlaInsightRepository


async def reaper_tick(session_factory: async_sessionmaker, max_retries: int) -> None:
    """Test wrapper: build repos from a session_factory and run the core helper."""
    async with session_factory.begin() as session:
        await _reaper_tick(
            SqlaInsightRepository(session),
            SqlaOutboxRepository(session),
            max_retries,
        )


pytestmark = pytest.mark.asyncio(loop_scope="module")


async def _seed_user(session_factory: async_sessionmaker, user_id: uuid.UUID) -> None:
    async with session_factory.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, plan, created_at)"
                " VALUES (:id, :email, :hash, 'free', NOW())"
            ),
            {"id": user_id, "email": f"reaper-{user_id.hex[:8]}@test.com", "hash": "x" * 60},
        )


async def _seed_insight(
    session_factory: async_sessionmaker,
    user_id: uuid.UUID,
    *,
    status: str = "processing",
    deadline_offset_seconds: int = -600,
    retry_count: int = 0,
) -> uuid.UUID:
    insight_id = uuid.uuid4()
    deadline = datetime.now(UTC) + timedelta(seconds=deadline_offset_seconds)
    async with session_factory.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO insights"
                " (id, user_id, period, period_year, period_month, status,"
                "  processing_deadline, retry_count, created_at)"
                " VALUES (:id, :user_id, 'monthly', 2026, 6, :status,"
                "  :deadline, :retry_count, NOW())"
            ),
            {
                "id": insight_id,
                "user_id": user_id,
                "status": status,
                "deadline": deadline,
                "retry_count": retry_count,
            },
        )
    return insight_id


async def _get_status(session_factory: async_sessionmaker, insight_id: uuid.UUID) -> dict:
    async with session_factory() as session:
        row = await session.execute(
            sa.text("SELECT status, retry_count, error_message FROM insights WHERE id = :id"),
            {"id": insight_id},
        )
        return dict(row.mappings().one())


async def _outbox_count(session_factory: async_sessionmaker, aggregate_id: str) -> int:
    async with session_factory() as session:
        result = await session.execute(
            sa.text("SELECT COUNT(*) FROM outbox_events WHERE aggregate_id = :id"),
            {"id": aggregate_id},
        )
        return result.scalar_one()


@pytest.fixture(scope="module")
async def session_factory(pg_url: str):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    await engine.dispose()


async def test_reaper_requeues_processing_insight_under_retry_limit(
    session_factory: async_sessionmaker,
) -> None:
    """Expired processing insight with retry_count < max → re-queued + outbox event."""
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)
    insight_id = await _seed_insight(session_factory, user_id, retry_count=0)

    await reaper_tick(session_factory, max_retries=3)

    row = await _get_status(session_factory, insight_id)
    assert row["status"] == "queued", f"expected queued, got {row['status']}"
    assert row["retry_count"] == 1
    assert row["error_message"] is None

    count = await _outbox_count(session_factory, str(insight_id))
    assert count == 1, f"expected 1 outbox event, got {count}"


async def test_reaper_fails_insight_at_retry_limit(
    session_factory: async_sessionmaker,
) -> None:
    """Expired processing insight with retry_count >= max → failed."""
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)
    insight_id = await _seed_insight(session_factory, user_id, retry_count=3)

    await reaper_tick(session_factory, max_retries=3)

    row = await _get_status(session_factory, insight_id)
    assert row["status"] == "failed", f"expected failed, got {row['status']}"
    assert "max retries" in (row["error_message"] or "")

    count = await _outbox_count(session_factory, str(insight_id))
    assert count == 0


async def test_reaper_leaves_non_expired_insight_untouched(
    session_factory: async_sessionmaker,
) -> None:
    """A processing insight whose deadline is in the future must not be touched."""
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)
    insight_id = await _seed_insight(session_factory, user_id, deadline_offset_seconds=900)

    await reaper_tick(session_factory, max_retries=3)

    row = await _get_status(session_factory, insight_id)
    assert row["status"] == "processing", f"expected processing, got {row['status']}"
    assert row["retry_count"] == 0


async def test_reaper_does_not_touch_queued_insights(
    session_factory: async_sessionmaker,
) -> None:
    """Already-queued insights must not be touched by the reaper."""
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)
    insight_id = await _seed_insight(
        session_factory, user_id, status="queued", deadline_offset_seconds=-600
    )

    await reaper_tick(session_factory, max_retries=3)

    row = await _get_status(session_factory, insight_id)
    assert row["status"] == "queued"
    assert row["retry_count"] == 0
