from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain.services.alert_threshold import (
    _FALLBACK_MIN,
    _MIN_AMOUNTS,
    is_alertworthy,
)
from app.domain.services.behavioral_shift_detector import (
    BehavioralShiftDetector,
    DetectedShift,
)
from app.domain.services.monthly_aggregator import MonthlyAggregation
from app.domain.services.portrait_aggregator import compute_window_averages

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_CURRENCIES = st.sampled_from(["USD", "EUR", "JPY", "GBP", "CNY", "KRW", "SGD", "AUD", "XYZ"])

_decimal_positive = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("1_000_000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)

_decimal_non_negative = st.decimals(
    min_value=Decimal("0"),
    max_value=Decimal("1_000_000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)


@st.composite
def top_categories(draw: st.DrawFn) -> list[tuple[str, Decimal, float]]:
    n = draw(st.integers(min_value=0, max_value=5))
    cats = []
    for _i in range(n):
        label = draw(
            st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",)))
        )
        amt = draw(_decimal_positive)
        pct = draw(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
        cats.append((label, amt, pct))
    return cats


@st.composite
def monthly_aggregation(draw: st.DrawFn, currency: str | None = None) -> MonthlyAggregation:
    ccy = currency if currency is not None else draw(_CURRENCIES)
    total_income = draw(_decimal_non_negative)
    total_expenses = draw(_decimal_non_negative)
    net_savings = total_income - total_expenses
    savings_rate = float(net_savings / total_income) if total_income > 0 else 0.0
    return MonthlyAggregation(
        year=draw(st.integers(min_value=2020, max_value=2030)),
        month=draw(st.integers(min_value=1, max_value=12)),
        currency=ccy,
        total_income=total_income,
        total_expenses=total_expenses,
        net_savings=net_savings,
        savings_rate=savings_rate,
        expense_volatility=draw(
            st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False)
        ),
        top_categories=draw(top_categories()),
        transaction_count=draw(st.integers(min_value=0, max_value=500)),
        avg_transaction_amount=draw(_decimal_non_negative),
        income_sources_count=draw(st.integers(min_value=0, max_value=10)),
        largest_single_expense=draw(_decimal_non_negative),
    )


# ---------------------------------------------------------------------------
# Group 1: BehavioralShiftDetector.detect
# ---------------------------------------------------------------------------


@given(
    current=monthly_aggregation(),
    history=st.lists(monthly_aggregation(), min_size=0, max_size=10),
)
@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
def test_detect_returns_list(
    current: MonthlyAggregation, history: list[MonthlyAggregation]
) -> None:
    """detect() never raises and always returns a list."""
    detector = BehavioralShiftDetector()
    result = detector.detect(current, history)
    assert isinstance(result, list)


@given(
    current=monthly_aggregation(),
    history=st.lists(monthly_aggregation(), min_size=2, max_size=10),
)
@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
def test_detect_shifts_have_valid_severity(
    current: MonthlyAggregation, history: list[MonthlyAggregation]
) -> None:
    """All detected shifts have severity in {'high', 'medium'}."""
    detector = BehavioralShiftDetector()
    shifts = detector.detect(current, history)
    for shift in shifts:
        assert shift.severity in {"high", "medium"}, f"Unexpected severity: {shift.severity!r}"


@given(
    current=monthly_aggregation(),
    history=st.lists(monthly_aggregation(), min_size=0, max_size=1),
)
@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
def test_detect_with_fewer_than_2_history_returns_empty(
    current: MonthlyAggregation, history: list[MonthlyAggregation]
) -> None:
    """Fewer than 2 history months always yields an empty shift list."""
    detector = BehavioralShiftDetector()
    assert detector.detect(current, history) == []


# ---------------------------------------------------------------------------
# Group 2: is_alertworthy
# ---------------------------------------------------------------------------


@given(
    shift_type=st.sampled_from(
        ["income_drop", "expense_spike", "savings_collapse", "savings_decline", "category_spike"]
    ),
    delta_pct=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    currency=_CURRENCIES,
    abs_change=_decimal_non_negative,
)
@settings(max_examples=40)
def test_is_alertworthy_false_for_medium_severity(
    shift_type: str, delta_pct: float, currency: str, abs_change: Decimal
) -> None:
    """Medium-severity shifts are never alertworthy."""
    shift = DetectedShift(
        type=shift_type,
        severity="medium",
        delta_pct=delta_pct,
        currency=currency,
        abs_change=abs_change,
    )
    assert not is_alertworthy(shift)


@given(
    shift_type=st.sampled_from(["income_drop", "expense_spike", "savings_collapse"]),
    delta_pct=st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    currency=_CURRENCIES,
    abs_change=_decimal_positive,
)
@settings(max_examples=40)
def test_is_alertworthy_high_severity_floor(
    shift_type: str, delta_pct: float, currency: str, abs_change: Decimal
) -> None:
    """High severity: alertworthy iff abs_change >= currency-specific floor."""
    shift = DetectedShift(
        type=shift_type,
        severity="high",
        delta_pct=delta_pct,
        currency=currency,
        abs_change=abs_change,
    )
    floor = _MIN_AMOUNTS.get(currency, _FALLBACK_MIN)
    result = is_alertworthy(shift)
    if abs_change >= floor:
        assert result, (
            f"Expected alertworthy for {currency} abs_change={abs_change} >= floor={floor}"
        )
    else:
        assert not result, (
            f"Expected NOT alertworthy for {currency} abs_change={abs_change} < floor={floor}"
        )


# ---------------------------------------------------------------------------
# Group 3: compute_window_averages
# ---------------------------------------------------------------------------


@given(
    months=st.lists(
        st.lists(monthly_aggregation(), min_size=0, max_size=4),
        min_size=0,
        max_size=6,
    )
)
@settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow])
def test_compute_window_averages_returns_dict(
    months: list[list[MonthlyAggregation]],
) -> None:
    """compute_window_averages never raises and always returns a dict."""
    result = compute_window_averages(months)
    assert isinstance(result, dict)
    # Each value is a dict mapping category label -> Decimal average
    for ccy, cat_map in result.items():
        assert isinstance(ccy, str)
        assert isinstance(cat_map, dict)
        for label, avg in cat_map.items():
            assert isinstance(label, str)
            assert isinstance(avg, Decimal)
