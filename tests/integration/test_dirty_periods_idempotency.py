import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.insights.dirty_period_repository import (
    SqlaDirtyPeriodRepository,
)
from app.outbound.adapters.sqla.transactions.dirty_period_marker import (
    SqlaDirtyPeriodMarker,
)
from app.outbound.persistence_sqla.mappings.all import map_tables
from app.outbound.persistence_sqla.mappings.dirty_period import dirty_periods

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def _seed_user(engine, user_id: uuid.UUID) -> None:
    """Insert a real users row so the FK on dirty_periods.user_id holds."""
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, plan, created_at)"
                " VALUES (:id, :email, :hash, 'free', NOW())"
            ),
            {
                "id": user_id,
                "email": f"dirty-{user_id}@example.com",
                "hash": "x" * 60,
            },
        )


async def _count_dirty(engine, user_id: uuid.UUID, year: int, month: int) -> int:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.select(sa.func.count())
            .select_from(dirty_periods)
            .where(dirty_periods.c.user_id == user_id)
            .where(dirty_periods.c.year == year)
            .where(dirty_periods.c.month == month)
        )
        return int(result.scalar_one())


async def test_repository_mark_dirty_is_idempotent_for_same_period(
    integration_settings, run_migrations
):
    """Arrange: a real user.
    Act:     mark the same (user, year, month) twice via the repository.
    Assert:  exactly one dirty_periods row exists — no duplicate, no error."""
    map_tables()
    engine = create_async_engine(integration_settings["database_settings"].database_url)
    user_id = UserId(uuid.uuid4())
    await _seed_user(engine, user_id.value)

    try:
        async with AsyncSession(engine) as session:
            repo = SqlaDirtyPeriodRepository(session)
            await repo.mark_dirty(user_id, 2026, 4)
            await repo.mark_dirty(user_id, 2026, 4)
            await session.commit()

        assert await _count_dirty(engine, user_id.value, 2026, 4) == 1
    finally:
        await engine.dispose()


async def test_marker_and_repository_converge_on_same_unique_target(
    integration_settings, run_migrations
):
    """Both write paths (transactions-BC marker + insights-BC repository) must
    converge on the same row when targeting the same (user, year, month).
    This pins that the index_elements tuple — not a constraint name — is what
    Postgres uses to detect the conflict."""
    map_tables()
    engine = create_async_engine(integration_settings["database_settings"].database_url)
    user_id = UserId(uuid.uuid4())
    await _seed_user(engine, user_id.value)

    try:
        async with AsyncSession(engine) as session:
            await SqlaDirtyPeriodMarker(session).mark_dirty(user_id, 2026, 5)
            await SqlaDirtyPeriodRepository(session).mark_dirty(user_id, 2026, 5)
            await session.commit()

        assert await _count_dirty(engine, user_id.value, 2026, 5) == 1
    finally:
        await engine.dispose()


async def test_different_months_create_independent_rows(integration_settings, run_migrations):
    """Sanity-check the negative case: distinct (year, month) tuples must
    NOT collide on the unique index."""
    map_tables()
    engine = create_async_engine(integration_settings["database_settings"].database_url)
    user_id = UserId(uuid.uuid4())
    await _seed_user(engine, user_id.value)

    try:
        async with AsyncSession(engine) as session:
            repo = SqlaDirtyPeriodRepository(session)
            await repo.mark_dirty(user_id, 2026, 4)
            await repo.mark_dirty(user_id, 2026, 5)
            await session.commit()

        assert await _count_dirty(engine, user_id.value, 2026, 4) == 1
        assert await _count_dirty(engine, user_id.value, 2026, 5) == 1
    finally:
        await engine.dispose()
