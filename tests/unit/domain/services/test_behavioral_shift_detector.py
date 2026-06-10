# tests/unit/domain/services/test_behavioral_shift_detector.py
from decimal import Decimal

import pytest

from app.domain.services.behavioral_shift_detector import (
    BehavioralShiftDetector,
    DetectedShift,
    ShiftThresholds,
    format_shift_text,
)
from app.domain.services.monthly_aggregator import MonthlyAggregation


def _agg(
    *,
    year: int = 2026,
    month: int = 1,
    income: float = 1000.0,
    expenses: float = 500.0,
    categories: list[tuple[str, float, float]] | None = None,
) -> MonthlyAggregation:
    total_income = Decimal(str(income))
    total_expenses = Decimal(str(expenses))
    net = total_income - total_expenses
    savings_rate = float(net / total_income) if total_income > 0 else 0.0
    top_cats = [
        (name, Decimal(str(amt)), pct)
        for name, amt, pct in (categories or [("Food", expenses, 1.0)])
    ]
    return MonthlyAggregation(
        year=year,
        month=month,
        currency="USD",
        total_income=total_income,
        total_expenses=total_expenses,
        net_savings=net,
        savings_rate=savings_rate,
        expense_volatility=0.0,
        top_categories=top_cats,
        transaction_count=10,
        avg_transaction_amount=Decimal("100"),
        income_sources_count=1,
        largest_single_expense=total_expenses,
    )


@pytest.fixture
def detector() -> BehavioralShiftDetector:
    return BehavioralShiftDetector()


def test_returns_empty_with_zero_history(detector: BehavioralShiftDetector):
    assert detector.detect(_agg(), []) == []


def test_returns_empty_with_one_history_month(detector: BehavioralShiftDetector):
    assert detector.detect(_agg(), [_agg()]) == []


def test_no_shifts_when_data_is_stable(detector: BehavioralShiftDetector):
    history = [_agg(income=1000, expenses=500) for _ in range(3)]
    current = _agg(income=1000, expenses=500)
    assert detector.detect(current, history) == []


def test_detects_income_drop_high(detector: BehavioralShiftDetector):
    history = [_agg(income=1000) for _ in range(3)]
    current = _agg(income=700)  # −30% < −20% → high
    shifts = detector.detect(current, history)
    income_shifts = [s for s in shifts if s.type == "income_drop"]
    assert len(income_shifts) == 1
    assert income_shifts[0].severity == "high"
    assert income_shifts[0].delta_pct < 0


def test_detects_income_drop_medium(detector: BehavioralShiftDetector):
    history = [_agg(income=1000) for _ in range(3)]
    current = _agg(income=870)  # −13%, between 10%–20% → medium
    shifts = detector.detect(current, history)
    income_shifts = [s for s in shifts if s.type == "income_drop"]
    assert len(income_shifts) == 1
    assert income_shifts[0].severity == "medium"


def test_no_income_drop_when_change_is_below_threshold(detector: BehavioralShiftDetector):
    history = [_agg(income=1000) for _ in range(3)]
    current = _agg(income=980)  # 2% — below medium threshold
    shifts = detector.detect(current, history)
    assert not any(s.type == "income_drop" for s in shifts)


def test_detects_expense_spike_high(detector: BehavioralShiftDetector):
    history = [_agg(expenses=500) for _ in range(3)]
    current = _agg(expenses=700)  # +40% > 30% → high
    shifts = detector.detect(current, history)
    expense_shifts = [s for s in shifts if s.type == "expense_spike"]
    assert len(expense_shifts) == 1
    assert expense_shifts[0].severity == "high"


def test_detects_expense_spike_medium(detector: BehavioralShiftDetector):
    history = [_agg(expenses=500) for _ in range(3)]
    current = _agg(expenses=600)  # +20% → medium
    shifts = detector.detect(current, history)
    expense_shifts = [s for s in shifts if s.type == "expense_spike"]
    assert len(expense_shifts) == 1
    assert expense_shifts[0].severity == "medium"


def test_detects_savings_collapse(detector: BehavioralShiftDetector):
    # avg savings_rate ≈ 0.5; current=0.2 → delta=0.3 > 0.15 → collapse
    history = [_agg(income=1000, expenses=500) for _ in range(3)]
    current = _agg(income=1000, expenses=800)
    shifts = detector.detect(current, history)
    collapse = [s for s in shifts if s.type == "savings_collapse"]
    assert len(collapse) == 1
    assert collapse[0].severity == "high"


def test_detects_savings_decline(detector: BehavioralShiftDetector):
    # avg savings_rate ≈ 0.5; current ≈ 0.38 → delta ≈ 0.12, between 0.08–0.15 → decline
    history = [_agg(income=1000, expenses=500) for _ in range(3)]
    current = _agg(income=1000, expenses=620)
    shifts = detector.detect(current, history)
    decline = [s for s in shifts if s.type == "savings_decline"]
    assert len(decline) == 1
    assert decline[0].severity == "medium"


def test_detects_category_spike_high(detector: BehavioralShiftDetector):
    history = [_agg(categories=[("Food", 100.0, 1.0)]) for _ in range(3)]
    current = _agg(categories=[("Food", 200.0, 1.0)])  # +100% > 40% → high
    shifts = detector.detect(current, history)
    cat_shifts = [s for s in shifts if s.type == "category_spike" and s.category == "Food"]
    assert len(cat_shifts) == 1
    assert cat_shifts[0].severity == "high"


def test_detects_category_spike_medium(detector: BehavioralShiftDetector):
    history = [_agg(categories=[("Food", 100.0, 1.0)]) for _ in range(3)]
    current = _agg(categories=[("Food", 130.0, 1.0)])  # +30% → medium
    shifts = detector.detect(current, history)
    cat_shifts = [s for s in shifts if s.type == "category_spike" and s.category == "Food"]
    assert len(cat_shifts) == 1
    assert cat_shifts[0].severity == "medium"


def test_no_category_spike_for_new_category_not_in_history(detector: BehavioralShiftDetector):
    history = [_agg(categories=[("Food", 100.0, 1.0)]) for _ in range(3)]
    current = _agg(categories=[("Travel", 500.0, 1.0)])
    shifts = detector.detect(current, history)
    assert not any(s.category == "Travel" for s in shifts)


def test_custom_thresholds_tighter_income_drop():
    detector = BehavioralShiftDetector(
        ShiftThresholds(income_drop_high=0.05, income_drop_medium=0.01)
    )
    history = [_agg(income=1000) for _ in range(3)]
    current = _agg(income=920)  # 8% drop → high with custom 5% threshold
    shifts = detector.detect(current, history)
    income_shifts = [s for s in shifts if s.type == "income_drop"]
    assert income_shifts[0].severity == "high"


def test_format_shift_text_returns_empty_for_no_shifts():
    assert format_shift_text(_agg(), []) == ""


def test_format_shift_text_income_drop_contains_month_and_severity():
    current = _agg(month=5)
    shifts = [DetectedShift(type="income_drop", severity="high", delta_pct=-0.25)]
    text = format_shift_text(current, shifts)
    assert "May" in text
    assert "Income dropped" in text
    assert "25.0%" in text
    assert "high" in text


def test_format_shift_text_expense_spike():
    current = _agg(month=3)
    shifts = [DetectedShift(type="expense_spike", severity="medium", delta_pct=0.18)]
    text = format_shift_text(current, shifts)
    assert "Expenses spiked" in text
    assert "medium" in text


def test_format_shift_text_category_spike_includes_category_name():
    current = _agg(month=1)
    shifts = [
        DetectedShift(type="category_spike", severity="high", delta_pct=0.55, category="Dining")
    ]
    text = format_shift_text(current, shifts)
    assert "Dining" in text
    assert "spiked" in text


def test_detects_income_drop_sets_currency_and_abs_change(detector: BehavioralShiftDetector):
    history = [_agg(income=1000) for _ in range(3)]
    current = _agg(income=700)
    shifts = detector.detect(current, history)
    s = next(s for s in shifts if s.type == "income_drop")
    assert s.currency == "USD"
    assert s.abs_change == Decimal("300")


def test_detects_expense_spike_sets_abs_change(detector: BehavioralShiftDetector):
    history = [_agg(expenses=500) for _ in range(3)]
    current = _agg(expenses=700)
    shifts = detector.detect(current, history)
    s = next(s for s in shifts if s.type == "expense_spike")
    assert s.currency == "USD"
    assert s.abs_change == Decimal("200")


def test_detects_category_spike_sets_abs_change(detector: BehavioralShiftDetector):
    history = [_agg(categories=[("Food", 100.0, 1.0)]) for _ in range(3)]
    current = _agg(categories=[("Food", 200.0, 1.0)])
    shifts = detector.detect(current, history)
    s = next(s for s in shifts if s.type == "category_spike")
    assert s.currency == "USD"
    assert s.abs_change == Decimal("100")


def test_savings_collapse_abs_change_is_monetary_estimate(detector: BehavioralShiftDetector):
    # avg_expenses=500, savings_delta≈0.3 → abs_change≈150
    history = [_agg(income=1000, expenses=500) for _ in range(3)]
    current = _agg(income=1000, expenses=800)
    shifts = detector.detect(current, history)
    s = next(s for s in shifts if s.type == "savings_collapse")
    assert s.currency == "USD"
    assert Decimal("100") < s.abs_change < Decimal("200")


def test_savings_decline_abs_change_is_monetary_estimate(detector: BehavioralShiftDetector):
    # avg savings_rate≈0.5; current≈0.38 → delta≈0.12, between 0.08–0.15 → decline
    # avg_expenses=500, abs_change≈0.12*500=60
    history = [_agg(income=1000, expenses=500) for _ in range(3)]
    current = _agg(income=1000, expenses=620)
    shifts = detector.detect(current, history)
    s = next(s for s in shifts if s.type == "savings_decline")
    assert s.currency == "USD"
    assert s.abs_change > Decimal("0")
    assert s.abs_change < Decimal("100")


def test_to_metadata_includes_currency_and_abs_change():
    s = DetectedShift(
        type="expense_spike",
        severity="high",
        delta_pct=0.4,
        currency="JPY",
        abs_change=Decimal("4200"),
    )
    m = s.to_metadata()
    assert m["currency"] == "JPY"
    assert m["abs_change"] == "4200"
