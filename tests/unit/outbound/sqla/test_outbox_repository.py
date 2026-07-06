"""Unit tests for SqlaOutboxRepository — UUIDv7 generation and sargable quota."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa

from app.application.common.outbox_event import OutboxEvent
from app.application.common.ports.quota_check import QuotaExceededError, QuotaResource
from app.domain.value_objects.enums import Plan
from app.domain.value_objects.ids import UserId
from app.outbound.adapters.sqla.common.outbox_repository import SqlaOutboxRepository
from app.outbound.adapters.sqla.common.quota_check import SqlaQuotaCheck
from app.outbound.persistence_sqla.mappings.all import map_tables

map_tables()


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_event() -> OutboxEvent:
    return OutboxEvent(
        event_type="TEST_EVENT",
        aggregate_id=str(uuid.uuid4()),
        payload={"key": "value"},
        occurred_at=datetime(2026, 6, 1, tzinfo=UTC),
        user_id=uuid.uuid4(),
    )


# ── Fix 1: outbox_events.id is a client-generated UUIDv7 ──────────────────────


@pytest.mark.asyncio
async def test_outbox_append_sets_uuid7_id() -> None:
    session = AsyncMock()
    session.execute = AsyncMock()

    repo = SqlaOutboxRepository(session)
    await repo.append(_make_event())

    call_args = session.execute.await_args
    # The INSERT statement is the first positional arg; values are bound params
    # when using .values() — extract via the compiled statement's params.
    stmt = call_args.args[0]
    # SQLAlchemy Insert.compile() exposes the bound params
    compiled = stmt.compile(dialect=sa.dialects.postgresql.dialect())
    params = compiled.params
    generated_id = params["id"]

    assert isinstance(generated_id, uuid.UUID), "id must be a uuid.UUID instance"
    assert generated_id.version == 7, (
        f"Expected UUIDv7 (version=7), got version={generated_id.version}"
    )


# ── Fix 3: quota_check uses half-open range, not EXTRACT ──────────────────────


async def _captured_quota_stmt(year: int, month: int) -> sa.Select:
    """Run the real SqlaQuotaCheck._count against a mocked session and capture the statement."""
    from unittest.mock import MagicMock

    session = MagicMock()
    result = MagicMock()
    result.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=result)
    check = SqlaQuotaCheck(session)
    await check._count(UserId(uuid.uuid4()), QuotaResource.TRANSACTIONS, year, month)
    return session.execute.await_args.args[0]


def _compile_literal(stmt: sa.Select) -> str:
    compiled = stmt.compile(
        dialect=sa.dialects.postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)


@pytest.mark.asyncio
async def test_quota_count_uses_range_predicate_not_extract() -> None:
    """The quota SELECT issued by _count must use >= / < bounds, not EXTRACT."""
    sql = _compile_literal(await _captured_quota_stmt(2026, 6))
    assert "EXTRACT" not in sql.upper(), (
        f"Quota count must not use EXTRACT — it prevents index use. Got SQL: {sql}"
    )
    assert "2026-06-01" in sql  # inclusive lower bound
    assert "2026-07-01" in sql  # exclusive upper bound


@pytest.mark.asyncio
async def test_quota_count_december_wraps_year() -> None:
    """December (month=12) must produce a range up to Jan 1 of the next year."""
    sql = _compile_literal(await _captured_quota_stmt(2026, 12))
    assert "EXTRACT" not in sql.upper()
    assert "2026-12-01" in sql
    assert "2027-01-01" in sql


@pytest.mark.asyncio
async def test_quota_check_and_increment_calls_count_then_raises() -> None:
    """check_and_increment raises QuotaExceededError when count >= limit."""
    from unittest.mock import MagicMock

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one = MagicMock(return_value=500)  # FREE plan limit
    session.execute = AsyncMock(return_value=result_mock)

    checker = SqlaQuotaCheck(session)
    with pytest.raises(QuotaExceededError):
        await checker.check_and_increment(
            user_id=UserId(uuid.uuid4()),
            resource=QuotaResource.TRANSACTIONS,
            plan=Plan.FREE,
        )
