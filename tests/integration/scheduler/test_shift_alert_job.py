from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.services.behavioral_shift_detector import BehavioralShiftDetector
from app.domain.value_objects.ids import UserId
from app.main.scheduler.shift_alert_tick import detect_shift_alerts_for_period
from app.outbound.adapters.sqla.insights.active_user_reader import SqlaActiveUserReader

pytestmark = pytest.mark.asyncio(loop_scope="module")


@pytest.fixture(scope="module")
async def session_factory(pg_url: str):
    engine = create_async_engine(pg_url)
    yield async_sessionmaker(engine, autoflush=False, expire_on_commit=False)
    await engine.dispose()


async def _seed_user(session_factory: async_sessionmaker, user_id: uuid.UUID) -> None:
    async with session_factory.begin() as session:
        await session.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, plan, created_at)"
                " VALUES (:id, :email, :hash, 'free', NOW())"
            ),
            {"id": user_id, "email": f"shift-{user_id.hex[:8]}@test.com", "hash": "x" * 60},
        )


async def _seed_expenses(
    session_factory: async_sessionmaker,
    user_id: uuid.UUID,
    year: int,
    month: int,
    total: Decimal,
) -> None:
    """Seed an income row + two daily expense rows summing to `total` for the month."""
    async with session_factory.begin() as session:
        rows = [
            (Decimal("3000.00"), "income", date(year, month, 1)),
            (total - Decimal("1.00"), "expense", date(year, month, 5)),
            (Decimal("1.00"), "expense", date(year, month, 6)),
        ]
        for amount, type_, dt in rows:
            await session.execute(
                sa.text(
                    "INSERT INTO transactions"
                    ' (id, user_id, amount_value, currency_code, type, "date", created_at)'
                    " VALUES (:id, :user_id, :amount, 'USD', :type, :date, NOW())"
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "amount": amount,
                    "type": type_,
                    "date": dt,
                },
            )


async def _alert_count(session_factory: async_sessionmaker, user_id: uuid.UUID) -> int:
    async with session_factory() as session:
        result = await session.execute(
            sa.text("SELECT COUNT(*) FROM user_alerts WHERE user_id = :id"),
            {"id": user_id},
        )
        return int(result.scalar_one())


# ── Active-user reader ──────────────────────────────────────────────────────


async def test_active_user_reader_returns_distinct_recent_users(
    session_factory: async_sessionmaker,
) -> None:
    recent = uuid.uuid4()
    old = uuid.uuid4()
    await _seed_user(session_factory, recent)
    await _seed_user(session_factory, old)

    # `recent` has transactions in May 2026; multiple rows must collapse to one id.
    await _seed_expenses(session_factory, recent, 2026, 5, Decimal("500.00"))
    # `old` only has transactions before the cutoff.
    await _seed_expenses(session_factory, old, 2025, 1, Decimal("500.00"))

    async with session_factory() as session:
        ids = await SqlaActiveUserReader(session).recently_active_user_ids(date(2026, 5, 1))

    assert UserId(recent) in ids
    assert UserId(old) not in ids
    # Distinctness: `recent` appears exactly once despite multiple transactions.
    assert ids.count(UserId(recent)) == 1


# ── Tick helper + idempotency ───────────────────────────────────────────────


async def test_tick_writes_alert_for_qualifying_shift_and_is_idempotent(
    session_factory: async_sessionmaker,
) -> None:
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)

    # 3 flat history months (~500) then a current-month spike (~900) → expense_spike.
    await _seed_expenses(session_factory, user_id, 2026, 2, Decimal("500.00"))
    await _seed_expenses(session_factory, user_id, 2026, 3, Decimal("500.00"))
    await _seed_expenses(session_factory, user_id, 2026, 4, Decimal("500.00"))
    await _seed_expenses(session_factory, user_id, 2026, 5, Decimal("900.00"))

    detector = BehavioralShiftDetector()

    await detect_shift_alerts_for_period(session_factory, detector, UserId(user_id), 2026, 5)
    first = await _alert_count(session_factory, user_id)
    assert first >= 1, "expected at least one alert written for the spike"

    # Running again writes nothing new (idempotent ON CONFLICT DO NOTHING).
    await detect_shift_alerts_for_period(session_factory, detector, UserId(user_id), 2026, 5)
    second = await _alert_count(session_factory, user_id)
    assert second == first, f"expected idempotent re-run, got {first} then {second}"


async def test_tick_writes_nothing_without_history(
    session_factory: async_sessionmaker,
) -> None:
    user_id = uuid.uuid4()
    await _seed_user(session_factory, user_id)
    # Only the current month, no history → use case stops, no alert.
    await _seed_expenses(session_factory, user_id, 2026, 5, Decimal("900.00"))

    detector = BehavioralShiftDetector()
    await detect_shift_alerts_for_period(session_factory, detector, UserId(user_id), 2026, 5)

    assert await _alert_count(session_factory, user_id) == 0
