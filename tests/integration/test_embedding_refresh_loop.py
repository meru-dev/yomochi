from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.value_objects.ids import UserId
from app.main.insight.refresh_tick import refresh_one_dirty_period
from app.outbound.persistence_sqla.mappings.all import map_tables

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module")
def pg_url() -> str:
    with PostgresContainer("pgvector/pgvector:pg16") as pg:
        url = pg.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        env = {**os.environ, "DATABASE_URL": url}
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=_ROOT,
            capture_output=True,
            check=True,
            env=env,
        )
        yield url


@pytest_asyncio.fixture
async def factory(pg_url: str) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    map_tables()
    engine = create_async_engine(pg_url, poolclass=NullPool)
    yield async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    await engine.dispose()


class _EmbedderFailingOnNth:
    """Returns a fixed vector for the first N calls, raises after."""

    def __init__(self, succeed_calls: int) -> None:
        self._budget = succeed_calls
        self.calls = 0

    async def embed(self, text: str) -> list[float]:
        self.calls += 1
        if self.calls > self._budget:
            raise RuntimeError("openai timeout")
        return [0.1] * 1536


async def _seed_user_and_txns(factory: async_sessionmaker[AsyncSession], user_email: str) -> UserId:
    """Insert a minimal users row + a handful of transactions for April 2026."""
    async with factory.begin() as session:
        user_id = uuid.uuid4()
        await session.execute(
            sa.text("""
                INSERT INTO users (id, email, password_hash, plan, created_at)
                VALUES (:id, :email, :hash, 'free', NOW())
            """),
            {"id": user_id, "email": user_email, "hash": "x" * 60},
        )
        for i in range(3):
            await session.execute(
                sa.text("""
                    INSERT INTO transactions
                        (id, user_id, amount_value, currency_code, type,
                         "date", created_at)
                    VALUES
                        (:id, :user_id, :amount, 'USD', 'expense',
                         :date, NOW())
                """),
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "amount": Decimal(f"{(i + 1) * 100}.00"),
                    "date": date(2026, 4, 1 + i),
                },
            )
    return UserId(user_id)


async def _seed_dirty(
    factory: async_sessionmaker[AsyncSession], user_id: UserId, year: int, month: int
) -> None:
    async with factory.begin() as session:
        await session.execute(
            sa.text("""
                INSERT INTO dirty_periods (user_id, year, month, created_at)
                VALUES (:user_id, :year, :month, NOW())
                ON CONFLICT DO NOTHING
            """),
            {"user_id": user_id.value, "year": year, "month": month},
        )


async def _count_chunks(factory, user_id: UserId, year: int, month: int) -> int:
    async with factory() as session:
        result = await session.execute(
            sa.text("""
                SELECT COUNT(*) FROM user_financial_chunks
                WHERE user_id = :user_id AND period_year = :year AND period_month = :month
                  AND chunk_type = 'monthly_summary'
            """),
            {"user_id": user_id.value, "year": year, "month": month},
        )
        return int(result.scalar_one())


async def _count_dirty(factory, user_id: UserId) -> int:
    async with factory() as session:
        result = await session.execute(
            sa.text("SELECT COUNT(*) FROM dirty_periods WHERE user_id = :user_id"),
            {"user_id": user_id.value},
        )
        return int(result.scalar_one())


async def test_failure_on_one_period_does_not_revert_committed_period(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    user1 = await _seed_user_and_txns(factory, f"u1-{uuid.uuid4().hex}@test")
    user2 = await _seed_user_and_txns(factory, f"u2-{uuid.uuid4().hex}@test")
    await _seed_dirty(factory, user1, 2026, 4)
    await _seed_dirty(factory, user2, 2026, 4)

    # 1 successful embed call covers user1's monthly_summary; behavioral_shift
    # needs >= 2 history months which we don't seed, so it's skipped.
    embedder = _EmbedderFailingOnNth(succeed_calls=1)
    detector = BehavioralShiftDetector()

    # Tick 1 — claims one of the two dirty periods. SKIP LOCKED ordering by id
    # makes it deterministic but we tolerate either order in the assertions.
    await refresh_one_dirty_period(factory, embedder, detector)

    # Tick 2 — claims the OTHER period; embedder raises on its first embed call
    # for this period.
    with pytest.raises(RuntimeError, match="openai timeout"):
        await refresh_one_dirty_period(factory, embedder, detector)

    # Exactly one user's chunk row was committed.
    chunks_user1 = await _count_chunks(factory, user1, 2026, 4)
    chunks_user2 = await _count_chunks(factory, user2, 2026, 4)
    assert chunks_user1 + chunks_user2 == 1, (
        f"expected exactly one committed chunk, got user1={chunks_user1} user2={chunks_user2}"
    )

    # The failed period's dirty row stayed; the successful one's was deleted.
    dirty_user1 = await _count_dirty(factory, user1)
    dirty_user2 = await _count_dirty(factory, user2)
    assert dirty_user1 + dirty_user2 == 1, (
        f"expected exactly one remaining dirty row, got user1={dirty_user1} user2={dirty_user2}"
    )


async def test_empty_queue_returns_false(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    # Drain anything left from prior test (module-scoped factory).
    async with factory.begin() as session:
        await session.execute(sa.text("DELETE FROM dirty_periods"))

    embedder = _EmbedderFailingOnNth(succeed_calls=10)
    detector = BehavioralShiftDetector()
    did_work = await refresh_one_dirty_period(factory, embedder, detector)
    assert did_work is False


async def test_multiple_dirty_periods_processed_in_single_gather(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    """Four dirty periods can be claimed concurrently via FOR UPDATE SKIP LOCKED."""
    import asyncio as _asyncio

    # Drain any leftovers.
    async with factory.begin() as session:
        await session.execute(sa.text("DELETE FROM dirty_periods"))
        await session.execute(sa.text("DELETE FROM user_financial_chunks"))

    user_ids = []
    for i in range(4):
        uid = await _seed_user_and_txns(factory, f"conc-{i}-{uuid.uuid4().hex}@test")
        user_ids.append(uid)
        await _seed_dirty(factory, uid, 2026, 7)

    embedder = _EmbedderFailingOnNth(succeed_calls=4)
    detector = BehavioralShiftDetector()

    results = await _asyncio.gather(
        *[refresh_one_dirty_period(factory, embedder, detector) for _ in range(4)],
        return_exceptions=True,
    )

    processed = sum(1 for r in results if r is True)
    assert processed == 4, f"Expected 4 processed, got {processed}. results={results}"

    async with factory() as session:
        result = await session.execute(
            sa.text("SELECT COUNT(*) FROM dirty_periods WHERE user_id = ANY(:ids)"),
            {"ids": [uid.value for uid in user_ids]},
        )
        remaining = int(result.scalar_one())
    assert remaining == 0
