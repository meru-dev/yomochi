import calendar
from datetime import date, timedelta

from app.domain.value_objects.enums import Recurrence


def compute_first_fire_date(
    start_date: date,
    recurrence: Recurrence,
    day_of_month: int | None,
    day_of_week: int | None,
    month: int | None,
) -> date:
    """Return the first fire date >= start_date for the given schedule."""
    if recurrence == Recurrence.WEEKLY:
        assert day_of_week is not None
        days_ahead = (day_of_week - start_date.weekday()) % 7
        return start_date + timedelta(days=days_ahead)

    if recurrence == Recurrence.MONTHLY:
        assert day_of_month is not None
        max_day = calendar.monthrange(start_date.year, start_date.month)[1]
        candidate = date(start_date.year, start_date.month, min(day_of_month, max_day))
        if candidate < start_date:
            m = start_date.month + 1
            y = start_date.year
            if m > 12:
                m, y = 1, y + 1
            max_day = calendar.monthrange(y, m)[1]
            candidate = date(y, m, min(day_of_month, max_day))
        return candidate

    if recurrence == Recurrence.YEARLY:
        assert day_of_month is not None
        assert month is not None
        max_day = calendar.monthrange(start_date.year, month)[1]
        candidate = date(start_date.year, month, min(day_of_month, max_day))
        if candidate < start_date:
            y = start_date.year + 1
            max_day = calendar.monthrange(y, month)[1]
            candidate = date(y, month, min(day_of_month, max_day))
        return candidate

    raise ValueError(f"Unsupported recurrence for RecurringRule: {recurrence}")


def advance_next_fire_date(
    current: date,
    recurrence: Recurrence,
    day_of_month: int | None,
    day_of_week: int | None,
    month: int | None,
) -> date:
    """Return the next fire date after `current`."""
    if recurrence == Recurrence.WEEKLY:
        return current + timedelta(days=7)

    if recurrence == Recurrence.MONTHLY:
        assert day_of_month is not None
        m = current.month + 1
        y = current.year
        if m > 12:
            m, y = 1, y + 1
        max_day = calendar.monthrange(y, m)[1]
        return date(y, m, min(day_of_month, max_day))

    if recurrence == Recurrence.YEARLY:
        assert day_of_month is not None
        assert month is not None
        y = current.year + 1
        max_day = calendar.monthrange(y, month)[1]
        return date(y, month, min(day_of_month, max_day))

    raise ValueError(f"Unsupported recurrence for RecurringRule: {recurrence}")
