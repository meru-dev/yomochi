import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.domain.entities.transaction import Transaction
from app.domain.value_objects.enums import TransactionType
from app.domain.value_objects.ids import TransactionId, UserId
from app.domain.value_objects.money import Currency, Money
from app.outbound.adapters.sqla.transactions.transaction_repository import (
    SqlaTransactionRepository,
)
from app.outbound.persistence_sqla.mappings.all import map_tables

map_tables()

pytestmark = pytest.mark.asyncio(loop_scope="module")


async def _seed_user(engine, user_id: uuid.UUID) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO users (id, email, password_hash, plan, created_at)"
                " VALUES (:id, :email, :hash, 'free', NOW())"
            ),
            {
                "id": user_id,
                "email": f"quota-atomicity-{user_id.hex[:8]}@test.com",
                "hash": "x" * 60,
            },
        )


def _make_tx(user_id: UserId) -> Transaction:
    return Transaction(
        id_=TransactionId(uuid.uuid4()),
        user_id=user_id,
        amount=Money(amount=Decimal("100.00"), currency=Currency(code="USD")),
        date=date(2026, 6, 1),
        type_=TransactionType.EXPENSE,
        merchant=None,
        notes=None,
        category_id=None,
        created_at=datetime.now(UTC),
    )


async def test_rolled_back_save_does_not_increment_count(
    integration_settings, run_migrations
) -> None:
    """Arrange: user with count=0.
    Act: save a transaction then rollback the session.
    Assert: count is still 0 — no phantom quota increment."""
    engine = create_async_engine(integration_settings["database_settings"].database_url)
    user_id = UserId(uuid.uuid4())
    await _seed_user(engine, user_id.value)

    try:
        # baseline
        async with AsyncSession(engine) as session:
            count_before = await SqlaTransactionRepository(session).count_created_in_month(
                user_id, 2026, 6
            )
        assert count_before == 0

        # save + flush (row visible within open TX) then explicit rollback
        async with AsyncSession(engine) as session:
            repo = SqlaTransactionRepository(session)
            await repo.save(_make_tx(user_id))
            await session.flush()
            await session.rollback()

        # count must still be 0
        async with AsyncSession(engine) as session:
            count_after = await SqlaTransactionRepository(session).count_created_in_month(
                user_id, 2026, 6
            )
        assert count_after == 0, f"quota leaked: expected 0, got {count_after}"

    finally:
        await engine.dispose()


async def test_committed_save_increments_count(integration_settings, run_migrations) -> None:
    """Positive control: a committed save increments the count exactly by 1."""
    engine = create_async_engine(integration_settings["database_settings"].database_url)
    user_id = UserId(uuid.uuid4())
    await _seed_user(engine, user_id.value)

    try:
        async with AsyncSession(engine) as session:
            await SqlaTransactionRepository(session).save(_make_tx(user_id))
            await session.commit()

        async with AsyncSession(engine) as session:
            count = await SqlaTransactionRepository(session).count_created_in_month(
                user_id, 2026, 6
            )
        assert count == 1

    finally:
        await engine.dispose()
