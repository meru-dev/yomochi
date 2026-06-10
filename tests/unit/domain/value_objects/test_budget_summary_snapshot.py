from decimal import Decimal

from app.domain.value_objects.budget_summary_snapshot import (
    BudgetSummarySnapshot,
    CurrencyTotals,
)


def _sample() -> BudgetSummarySnapshot:
    return BudgetSummarySnapshot(
        per_currency=(
            CurrencyTotals(
                currency="JPY",
                income=Decimal("0"),
                expense=Decimal("12345"),
                count=5,
            ),
            CurrencyTotals(
                currency="USD",
                income=Decimal("100.50"),
                expense=Decimal("42.99"),
                count=2,
            ),
        )
    )


def test_to_json_serialises_decimal_as_string() -> None:
    snap = _sample()
    payload = snap.to_json()
    assert payload == [
        {"currency": "JPY", "income": "0", "expense": "12345", "count": 5},
        {"currency": "USD", "income": "100.50", "expense": "42.99", "count": 2},
    ]


def test_from_json_round_trip() -> None:
    snap = _sample()
    restored = BudgetSummarySnapshot.from_json(snap.to_json())
    assert restored == snap


def test_from_json_returns_none_on_empty_list() -> None:
    assert BudgetSummarySnapshot.from_json([]) is None


def test_from_json_returns_none_on_none_input() -> None:
    assert BudgetSummarySnapshot.from_json(None) is None


def test_from_json_parses_string_decimals() -> None:
    raw = [
        {"currency": "EUR", "income": "1.99", "expense": "0.01", "count": 1},
    ]
    snap = BudgetSummarySnapshot.from_json(raw)
    assert snap is not None
    assert snap.per_currency[0].income == Decimal("1.99")
    assert snap.per_currency[0].expense == Decimal("0.01")
    assert snap.per_currency[0].count == 1
