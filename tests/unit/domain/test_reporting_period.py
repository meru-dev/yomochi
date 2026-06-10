from datetime import date

import pytest

from app.domain.value_objects.reporting_period import MonthPeriod, TrendWindow


class TestMonthPeriod:
    def test_rejects_bad_month(self) -> None:
        with pytest.raises(ValueError):
            MonthPeriod(year=2026, month=0)
        with pytest.raises(ValueError):
            MonthPeriod(year=2026, month=13)

    def test_rejects_bad_year(self) -> None:
        with pytest.raises(ValueError):
            MonthPeriod(year=1800, month=1)

    def test_bounds_past_month_returns_full_calendar_month(self) -> None:
        period = MonthPeriod(year=2026, month=2)
        start, end = period.bounds_clipped_to(today=date(2026, 5, 15))
        assert start == date(2026, 2, 1)
        assert end == date(2026, 2, 28)

    def test_bounds_leap_february(self) -> None:
        period = MonthPeriod(year=2024, month=2)
        _start, end = period.bounds_clipped_to(today=date(2024, 5, 15))
        assert end == date(2024, 2, 29)

    def test_bounds_current_month_clips_to_today(self) -> None:
        period = MonthPeriod(year=2026, month=5)
        start, end = period.bounds_clipped_to(today=date(2026, 5, 15))
        assert start == date(2026, 5, 1)
        assert end == date(2026, 5, 15)

    def test_bounds_future_month_clips_to_today(self) -> None:
        period = MonthPeriod(year=2026, month=8)
        start, end = period.bounds_clipped_to(today=date(2026, 5, 15))
        assert start == date(2026, 8, 1)
        assert end == date(2026, 5, 15)


class TestTrendWindow:
    def test_rejects_bad_granularity(self) -> None:
        with pytest.raises(ValueError):
            TrendWindow(granularity="quarter", bucket_count=4, end=date(2026, 5, 15))  # type: ignore[arg-type]

    def test_rejects_bucket_count_out_of_range(self) -> None:
        with pytest.raises(ValueError):
            TrendWindow(granularity="month", bucket_count=0, end=date(2026, 5, 15))
        with pytest.raises(ValueError):
            TrendWindow(granularity="week", bucket_count=53, end=date(2026, 5, 15))
