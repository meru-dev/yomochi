# tests/unit/domain/services/test_monthly_aggregator.py
from decimal import Decimal

import pytest

from app.domain.services.monthly_aggregator import (
    TransactionRow,
    aggregate,
    compute_semantic_hash,
    format_monthly_summary,
)


def _row(
    amount: str, currency: str, type_: str, cat: str | None = None, day: int = 1
) -> TransactionRow:
    return TransactionRow(
        amount=Decimal(amount),
        currency=currency,
        type_=type_,
        category_label=cat,
        day_of_month=day,
    )


# ── aggregate() ──────────────────────────────────────────────────────────────


def test_aggregate_empty_returns_empty_list():
    assert aggregate(2026, 5, []) == []


def test_aggregate_single_currency_totals():
    rows = [
        _row("1000", "USD", "income", "Salary", 1),
        _row("200", "USD", "expense", "Food", 5),
        _row("300", "USD", "expense", "Rent", 1),
    ]
    result = aggregate(2026, 5, rows)
    assert len(result) == 1
    agg = result[0]
    assert agg.currency == "USD"
    assert agg.total_income == Decimal("1000")
    assert agg.total_expenses == Decimal("500")
    assert agg.net_savings == Decimal("500")
    assert agg.savings_rate == pytest.approx(0.5)
    assert agg.transaction_count == 3
    assert agg.year == 2026
    assert agg.month == 5


def test_aggregate_multi_currency_produces_one_agg_per_currency():
    rows = [
        _row("1000", "USD", "income"),
        _row("500", "JPY", "expense", "Food"),
    ]
    result = aggregate(2026, 5, rows)
    assert len(result) == 2
    assert {r.currency for r in result} == {"USD", "JPY"}


def test_aggregate_expense_only_savings_rate_is_zero():
    rows = [_row("100", "EUR", "expense", "Food")]
    result = aggregate(2026, 5, rows)
    assert result[0].total_income == Decimal("0")
    assert result[0].savings_rate == 0.0


def test_aggregate_categories_sorted_by_amount_descending():
    rows = [
        _row("100", "USD", "expense", "Food"),
        _row("50", "USD", "expense", "Food"),
        _row("200", "USD", "expense", "Rent"),
        _row("500", "USD", "income"),
    ]
    result = aggregate(2026, 5, rows)
    cats = result[0].top_categories
    assert cats[0][0] == "Rent"
    assert cats[1][0] == "Food"


def test_aggregate_category_amounts_summed():
    rows = [
        _row("100", "USD", "expense", "Food"),
        _row("50", "USD", "expense", "Food"),
        _row("500", "USD", "income"),
    ]
    result = aggregate(2026, 5, rows)
    food = next(c for c in result[0].top_categories if c[0] == "Food")
    assert food[1] == Decimal("150")


def test_aggregate_largest_single_expense():
    rows = [
        _row("50", "USD", "expense", "Food"),
        _row("500", "USD", "expense", "Rent"),
        _row("100", "USD", "expense", "Gym"),
    ]
    assert aggregate(2026, 5, rows)[0].largest_single_expense == Decimal("500")


def test_aggregate_volatility_zero_when_single_expense_day():
    rows = [
        _row("100", "USD", "expense", "Food", 1),
        _row("200", "USD", "expense", "Rent", 1),
    ]
    assert aggregate(2026, 5, rows)[0].expense_volatility == 0.0


def test_aggregate_volatility_nonzero_with_spread_expenses():
    rows = [
        _row("10", "USD", "expense", "Food", 1),
        _row("1000", "USD", "expense", "Rent", 15),
    ]
    assert aggregate(2026, 5, rows)[0].expense_volatility > 0.3


def test_aggregate_income_sources_count_distinct_categories():
    rows = [
        _row("1000", "USD", "income", "Salary"),
        _row("200", "USD", "income", "Freelance"),
        _row("50", "USD", "expense", "Food"),
    ]
    assert aggregate(2026, 5, rows)[0].income_sources_count == 2


# ── compute_semantic_hash() ──────────────────────────────────────────────────


def test_compute_semantic_hash_empty_returns_empty_string():
    assert compute_semantic_hash([]) == ""


def test_compute_semantic_hash_same_data_deterministic():
    rows = [
        _row("1000", "USD", "income"),
        _row("300", "USD", "expense", "Food"),
    ]
    aggs = aggregate(2026, 5, rows)
    assert compute_semantic_hash(aggs) == compute_semantic_hash(aggs)


def test_compute_semantic_hash_is_sha256_length():
    aggs = aggregate(2026, 5, [_row("100", "USD", "expense")])
    h = compute_semantic_hash(aggs)
    assert len(h) == 64


def test_compute_semantic_hash_changes_when_amounts_change():
    rows1 = [_row("1000", "USD", "income")]
    rows2 = [_row("2000", "USD", "income")]
    h1 = compute_semantic_hash(aggregate(2026, 5, rows1))
    h2 = compute_semantic_hash(aggregate(2026, 5, rows2))
    assert h1 != h2


# ── format_monthly_summary() ─────────────────────────────────────────────────


def test_format_monthly_summary_empty_returns_empty_string():
    assert format_monthly_summary([]) == ""


def test_format_monthly_summary_contains_month_year():
    aggs = aggregate(2026, 5, [_row("1000", "USD", "income")])
    text = format_monthly_summary(aggs)
    assert "May 2026" in text


def test_format_monthly_summary_contains_income_and_expenses():
    rows = [
        _row("1000", "USD", "income"),
        _row("400", "USD", "expense", "Food"),
    ]
    text = format_monthly_summary(aggregate(2026, 5, rows))
    assert "1000 USD" in text
    assert "400 USD" in text


def test_format_monthly_summary_contains_category_name():
    rows = [
        _row("500", "USD", "income"),
        _row("200", "USD", "expense", "Dining"),
    ]
    text = format_monthly_summary(aggregate(2026, 5, rows))
    assert "Dining" in text


def test_format_monthly_summary_volatility_label_low():
    rows = [_row("100", "USD", "expense", "Food", 1)]
    text = format_monthly_summary(aggregate(2026, 5, rows))
    assert "low" in text
