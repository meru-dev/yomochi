# tests/unit/domain/services/test_portrait_aggregator.py
from decimal import Decimal

from app.domain.services.monthly_aggregator import MonthlyAggregation
from app.domain.services.portrait_aggregator import compute_window_averages, format_portrait_text


def _agg(
    year: int = 2026,
    month: int = 5,
    currency: str = "JPY",
    expenses: str = "50000",
    income: str = "100000",
    categories: list[tuple[str, str, float]] | None = None,
    tx_count: int = 30,
) -> MonthlyAggregation:
    if categories is None:
        categories = [("Food", "30000", 0.6), ("Transport", "20000", 0.4)]
    top_cats = [(cat, Decimal(amt), pct) for cat, amt, pct in categories]
    exp = Decimal(expenses)
    inc = Decimal(income)
    net = inc - exp
    return MonthlyAggregation(
        year=year,
        month=month,
        currency=currency,
        total_income=inc,
        total_expenses=exp,
        net_savings=net,
        savings_rate=float(net / inc) if inc > 0 else 0.0,
        expense_volatility=0.1,
        top_categories=top_cats,
        transaction_count=tx_count,
        avg_transaction_amount=exp / tx_count,
        income_sources_count=1,
        largest_single_expense=max(Decimal(amt) for _, amt, _ in categories),
    )


# ── compute_window_averages ──────────────────────────────────────────────────


def test_window_averages_single_month():
    months = [[_agg(categories=[("Food", "30000", 0.6), ("Coffee", "10000", 0.2)])]]
    result = compute_window_averages(months)
    assert result["JPY"]["Food"] == Decimal("30000")
    assert result["JPY"]["Coffee"] == Decimal("10000")


def test_window_averages_three_months_computes_mean():
    months = [
        [_agg(month=2, categories=[("Food", "30000", 0.6)])],
        [_agg(month=3, categories=[("Food", "36000", 0.6)])],
        [_agg(month=4, categories=[("Food", "42000", 0.6)])],
    ]
    result = compute_window_averages(months)
    # (30000 + 36000 + 42000) / 3 = 36000
    assert result["JPY"]["Food"] == Decimal("36000")


def test_window_averages_empty_input_returns_empty():
    assert compute_window_averages([]) == {}


def test_window_averages_multi_currency_kept_separate():
    months = [
        [
            _agg(currency="JPY", categories=[("Food", "30000", 0.6)]),
            _agg(currency="USD", categories=[("Food", "300", 0.6)]),
        ]
    ]
    result = compute_window_averages(months)
    assert result["JPY"]["Food"] == Decimal("30000")
    assert result["USD"]["Food"] == Decimal("300")


# ── format_portrait_text ─────────────────────────────────────────────────────


def test_format_portrait_empty_recent_returns_empty():
    assert format_portrait_text([], []) == ""


def test_format_portrait_includes_month_year_header():
    text = format_portrait_text(
        [_agg(year=2026, month=5)],
        [[_agg(month=2)], [_agg(month=3)], [_agg(month=4)]],
    )
    assert "May 2026" in text


def test_format_portrait_shift_above_threshold_shown():
    # Coffee ↑69%: recent=14200, baseline avg=(8000+8400+8800)/3=8400
    recent = [_agg(month=5, categories=[("Coffee", "14200", 0.3)])]
    baseline = [
        [_agg(month=2, categories=[("Coffee", "8000", 0.2)])],
        [_agg(month=3, categories=[("Coffee", "8400", 0.2)])],
        [_agg(month=4, categories=[("Coffee", "8800", 0.2)])],
    ]
    text = format_portrait_text(recent, baseline)
    assert "↑" in text
    assert "Coffee" in text
    assert "stable" not in text


def test_format_portrait_shift_below_threshold_shows_stable():
    # Food +0.3% change: below 10% threshold
    recent = [_agg(month=5, categories=[("Food", "30100", 0.6)])]
    baseline = [[_agg(month=4, categories=[("Food", "30000", 0.6)])]]
    text = format_portrait_text(recent, baseline)
    assert "stable" in text
    assert "↑" not in text
    assert "↓" not in text


def test_format_portrait_no_baseline_omits_comparison_words():
    text = format_portrait_text([_agg(month=5)], [])
    assert "baseline" not in text
    assert "stable" not in text
    assert "Food" in text


def test_format_portrait_includes_total_and_tx_count():
    text = format_portrait_text([_agg(month=5, tx_count=47)], [])
    assert "47" in text
    assert "50000" in text  # total_expenses


def test_format_portrait_downward_shift_uses_down_arrow():
    # Entertainment ↓15%: recent=9800, baseline=11500
    recent = [_agg(month=5, categories=[("Entertainment", "9800", 0.2)])]
    baseline = [[_agg(month=4, categories=[("Entertainment", "11500", 0.2)])]]
    text = format_portrait_text(recent, baseline)
    assert "↓" in text
