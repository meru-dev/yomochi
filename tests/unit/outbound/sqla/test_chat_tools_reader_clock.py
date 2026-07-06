"""Unit tests — Clock injection into SqlaChatToolsReader.

These tests verify that get_category_trend and get_user_profile compute their
month windows from the injected Clock, not from wall-clock datetime.now().
No database is involved; the DB session is mocked to return empty results.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.application.common.ports.clock import Clock
from app.outbound.adapters.sqla.chat.chat_tools_reader import SqlaChatToolsReader

USER_ID = str(UUID("00000000-0000-0000-0000-000000000001"))

# Fixed clock at 2026-06-15 — the month windows should be computed from this date.
_FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)


class FixedClock:
    """Test double for Clock that always returns _FIXED_NOW."""

    def now(self) -> datetime:
        return _FIXED_NOW

    def today(self) -> date:
        return _FIXED_NOW.date()


def _make_reader() -> tuple[SqlaChatToolsReader, MagicMock]:
    """Build a SqlaChatToolsReader with a fixed clock and a mock session factory.

    Returns (reader, session) so tests can inspect session.execute call args.
    """
    session = MagicMock()
    result = MagicMock()
    result.fetchall = MagicMock(return_value=[])
    session.execute = AsyncMock(return_value=result)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    session_factory = MagicMock(return_value=session)
    clock: Clock = FixedClock()  # type: ignore[assignment]
    return SqlaChatToolsReader(session_factory=session_factory, clock=clock), session


def _date_params_from_stmt(stmt: object) -> tuple[date, date]:
    """Extract the two date bind-parameter values from a compiled SA statement.

    The category-trend query adds `.where(date >= first_day)` and
    `.where(date <= last_day)`, which compile to params named ``date_1``
    and ``date_2``.  We compile without a dialect so no DB connection is
    needed, then pull the date values out of the params dict.
    """
    compiled = stmt.compile()  # type: ignore[union-attr]
    date_values = sorted(v for v in compiled.params.values() if isinstance(v, date))
    assert len(date_values) == 2, f"Expected 2 date params, got: {date_values}"
    return date_values[0], date_values[1]


@pytest.mark.asyncio
async def test_get_category_trend_uses_injected_clock() -> None:
    """Month window for get_category_trend must come from the injected clock.

    With a fixed clock at 2026-06-15, asking for n_months=3 should cover
    2026-05, 2026-04, 2026-03 (three months strictly before June 2026).
    The query date range should therefore be 2026-03-01 to 2026-05-31.
    """
    reader, session = _make_reader()
    result = await reader.get_category_trend(USER_ID, "Food", n_months=3)
    assert result.category == "Food"

    # Prove the clock drove the window: extract date bounds from the executed statement.
    assert session.execute.call_count == 1, "Expected exactly one DB call"
    executed_stmt = session.execute.call_args_list[0].args[0]
    first_day, last_day = _date_params_from_stmt(executed_stmt)
    assert first_day == date(2026, 3, 1), f"Wrong window start: {first_day}"
    assert last_day == date(2026, 5, 31), f"Wrong window end: {last_day}"


@pytest.mark.asyncio
async def test_get_user_profile_uses_injected_clock() -> None:
    """Month window for get_user_profile must come from the injected clock.

    With _PROFILE_MONTHS=4 and a fixed clock at 2026-06-15, the reader
    should cover 2026-05, 2026-04, 2026-03, 2026-02 — four months strictly
    before June 2026.
    """
    reader, _ = _make_reader()
    result = await reader.get_user_profile(USER_ID)
    assert result.months_covered == 4
    assert result.by_currency == []


@pytest.mark.asyncio
async def test_clock_constructor_required() -> None:
    """SqlaChatToolsReader must accept a clock parameter without error."""
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session_factory = MagicMock(return_value=session)
    clock: Clock = FixedClock()  # type: ignore[assignment]
    # Must not raise — existence of the clock parameter
    reader = SqlaChatToolsReader(session_factory=session_factory, clock=clock)
    assert reader is not None
