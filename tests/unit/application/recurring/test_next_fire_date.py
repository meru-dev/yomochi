from datetime import date

from app.application.recurring.next_fire_date import (
    advance_next_fire_date,
    compute_first_fire_date,
)
from app.domain.value_objects.enums import Recurrence

# ── compute_first_fire_date ──────────────────────────────────────────────────


def test_weekly_start_on_exact_day() -> None:
    # 2026-05-25 is Monday (weekday 0)
    result = compute_first_fire_date(date(2026, 5, 25), Recurrence.WEEKLY, None, 0, None)
    assert result == date(2026, 5, 25)


def test_weekly_start_before_target_weekday() -> None:
    # 2026-05-21 is Thursday (weekday 3); next Monday is 2026-05-25
    result = compute_first_fire_date(date(2026, 5, 21), Recurrence.WEEKLY, None, 0, None)
    assert result == date(2026, 5, 25)


def test_monthly_day_in_future_within_month() -> None:
    result = compute_first_fire_date(date(2026, 5, 10), Recurrence.MONTHLY, 25, None, None)
    assert result == date(2026, 5, 25)


def test_monthly_day_already_past_advances_to_next_month() -> None:
    result = compute_first_fire_date(date(2026, 5, 28), Recurrence.MONTHLY, 15, None, None)
    assert result == date(2026, 6, 15)


def test_monthly_day_28_in_february() -> None:
    result = compute_first_fire_date(date(2027, 2, 1), Recurrence.MONTHLY, 28, None, None)
    assert result == date(2027, 2, 28)


def test_yearly_in_future_same_year() -> None:
    result = compute_first_fire_date(date(2026, 5, 21), Recurrence.YEARLY, 1, None, 12)
    assert result == date(2026, 12, 1)


def test_yearly_already_past_advances_to_next_year() -> None:
    result = compute_first_fire_date(date(2026, 5, 21), Recurrence.YEARLY, 1, None, 3)
    assert result == date(2027, 3, 1)


# ── advance_next_fire_date ───────────────────────────────────────────────────


def test_advance_weekly() -> None:
    result = advance_next_fire_date(date(2026, 5, 25), Recurrence.WEEKLY, None, 0, None)
    assert result == date(2026, 6, 1)


def test_advance_monthly_normal() -> None:
    result = advance_next_fire_date(date(2026, 5, 15), Recurrence.MONTHLY, 15, None, None)
    assert result == date(2026, 6, 15)


def test_advance_monthly_across_year() -> None:
    result = advance_next_fire_date(date(2026, 12, 15), Recurrence.MONTHLY, 15, None, None)
    assert result == date(2027, 1, 15)


def test_advance_monthly_day_28_feb_caps() -> None:
    # day_of_month=28, advancing from Jan → Feb (28 days in 2027)
    result = advance_next_fire_date(date(2027, 1, 28), Recurrence.MONTHLY, 28, None, None)
    assert result == date(2027, 2, 28)


def test_advance_yearly() -> None:
    result = advance_next_fire_date(date(2026, 6, 1), Recurrence.YEARLY, 1, None, 6)
    assert result == date(2027, 6, 1)
