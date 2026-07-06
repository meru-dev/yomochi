"""Unit tests for ChatTools port shape and the pure aggregation helpers in SqlaChatToolsReader.

These tests use in-memory fakes (no database) to verify:
- The _build_currency_summaries helper aggregates correctly.
- The port shape is correct (Protocol duck-typing check).
- FakeChatTools satisfies the ChatTools Protocol.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.application.chat.ports.chat_tools import (
    CategoryAmount,
    CategoryInfo,
    CategoryTrendPoint,
    CategoryTrendResult,
    ChatTools,
    CurrencyMonthSummary,
    ListCategoriesResult,
    MonthSummaryResult,
    SearchTransactionsResult,
    SpendWindowResult,
    TransactionMatch,
    UserProfileResult,
    to_jsonable,
)
from app.application.insights.ports.budget_summary_reader import BudgetTransactionRow
from app.outbound.adapters.sqla.chat.chat_tools_reader import _build_currency_summaries

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(
    amount: str,
    currency: str = "USD",
    type_: str = "expense",
    category: str | None = "Food",
    day: int = 1,
) -> BudgetTransactionRow:
    return BudgetTransactionRow(
        amount=Decimal(amount),
        currency=currency,
        type_=type_,
        category_label=category,
        day_of_month=day,
    )


# ---------------------------------------------------------------------------
# _build_currency_summaries unit tests
# ---------------------------------------------------------------------------


def test_build_currency_summaries_empty_returns_empty() -> None:
    result = _build_currency_summaries(2026, 5, [])
    assert result == []


def test_build_currency_summaries_single_currency() -> None:
    rows = [
        _row("100.00", "USD", "income", None, 1),
        _row("30.00", "USD", "expense", "Food", 2),
        _row("20.00", "USD", "expense", "Transport", 3),
    ]
    summaries = _build_currency_summaries(2026, 5, rows)
    assert len(summaries) == 1
    s = summaries[0]
    assert s.currency == "USD"
    assert s.total_income == Decimal("100.00")
    assert s.total_expenses == Decimal("50.00")
    assert s.net_savings == Decimal("50.00")
    assert abs(s.savings_rate - 0.5) < 0.001
    assert s.transaction_count == 3
    cat_names = {c.category for c in s.top_categories}
    assert cat_names == {"Food", "Transport"}


def test_build_currency_summaries_multi_currency() -> None:
    rows = [
        _row("100.00", "USD", "income", None, 1),
        _row("40.00", "USD", "expense", "Food", 2),
        _row("5000", "JPY", "income", None, 1),
        _row("1000", "JPY", "expense", "Food", 2),
    ]
    summaries = _build_currency_summaries(2026, 5, rows)
    assert len(summaries) == 2
    by_currency = {s.currency: s for s in summaries}
    assert by_currency["USD"].total_income == Decimal("100.00")
    assert by_currency["JPY"].total_income == Decimal("5000")


def test_build_currency_summaries_top_categories_pct() -> None:
    rows = [
        _row("100.00", "USD", "income", None, 1),
        _row("60.00", "USD", "expense", "Food", 2),
        _row("40.00", "USD", "expense", "Transport", 3),
    ]
    summaries = _build_currency_summaries(2026, 5, rows)
    cats = {c.category: c for c in summaries[0].top_categories}
    assert abs(cats["Food"].pct_of_expenses - 0.6) < 0.001
    assert abs(cats["Transport"].pct_of_expenses - 0.4) < 0.001


def test_build_currency_summaries_no_expenses() -> None:
    rows = [
        _row("200.00", "USD", "income", None, 1),
    ]
    summaries = _build_currency_summaries(2026, 5, rows)
    assert summaries[0].total_expenses == Decimal("0")
    assert summaries[0].net_savings == Decimal("200.00")
    assert summaries[0].savings_rate == 1.0


# ---------------------------------------------------------------------------
# FakeChatTools — verifies Protocol duck-typing
# ---------------------------------------------------------------------------


class FakeChatTools:
    """In-memory fake satisfying the ChatTools Protocol."""

    async def get_month_summary(self, user_id: str, year: int, month: int) -> MonthSummaryResult:
        return MonthSummaryResult(year=year, month=month, by_currency=[])

    async def get_category_trend(
        self, user_id: str, category: str, n_months: int
    ) -> CategoryTrendResult:
        return CategoryTrendResult(category=category, series=[])

    async def get_spend_window(
        self, user_id: str, start_date: date, end_date: date
    ) -> SpendWindowResult:
        return SpendWindowResult(start_date=start_date, end_date=end_date, by_currency=[])

    async def get_user_profile(self, user_id: str) -> UserProfileResult:
        return UserProfileResult(months_covered=0, by_currency=[])

    async def search_transactions(
        self, user_id: str, text: str, limit: int
    ) -> SearchTransactionsResult:
        return SearchTransactionsResult(query=text, matches=[])

    async def list_categories(self, user_id: str) -> ListCategoriesResult:
        return ListCategoriesResult(categories=[])


def test_fake_chat_tools_satisfies_protocol() -> None:
    """FakeChatTools must satisfy the ChatTools Protocol (runtime_checkable)."""
    fake = FakeChatTools()
    assert isinstance(fake, ChatTools)


async def test_fake_chat_tools_get_month_summary() -> None:
    fake = FakeChatTools()
    result = await fake.get_month_summary("00000000-0000-0000-0000-000000000001", 2026, 5)
    assert result.year == 2026
    assert result.month == 5
    assert result.by_currency == []


async def test_fake_chat_tools_search_transactions() -> None:
    fake = FakeChatTools()
    result = await fake.search_transactions("00000000-0000-0000-0000-000000000001", "coffee", 10)
    assert result.query == "coffee"
    assert result.matches == []


# ---------------------------------------------------------------------------
# Dataclass frozen / JSON-serialisable
# ---------------------------------------------------------------------------


def test_month_summary_result_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    r = MonthSummaryResult(year=2026, month=5, by_currency=[])
    with pytest.raises(FrozenInstanceError):
        r.year = 2025  # type: ignore[misc]


def test_transaction_match_fields() -> None:
    tm = TransactionMatch(
        transaction_id="abc",
        date=date(2026, 5, 1),
        amount=Decimal("9.99"),
        currency="USD",
        type_="expense",
        merchant="Starbucks",
        notes=None,
        category="Coffee",
    )
    assert tm.merchant == "Starbucks"
    assert tm.notes is None


def test_category_amount_currency_field() -> None:
    ca = CategoryAmount(
        category="Food",
        amount=Decimal("50"),
        currency="EUR",
        pct_of_expenses=0.5,
    )
    assert ca.currency == "EUR"


# ---------------------------------------------------------------------------
# to_jsonable — JSON serialisation round-trip tests
# ---------------------------------------------------------------------------


def test_to_jsonable_transaction_match_round_trips() -> None:
    """TransactionMatch (has Decimal + date fields) must survive json.dumps via to_jsonable."""
    import json

    tm = TransactionMatch(
        transaction_id="abc-123",
        date=date(2026, 3, 15),
        amount=Decimal("9.99"),
        currency="USD",
        type_="expense",
        merchant="Starbucks",
        notes=None,
        category="Coffee",
    )
    payload = to_jsonable(tm)
    serialised = json.dumps(payload)  # must not raise
    assert '"9.99"' in serialised, "Decimal must be serialised as string"
    assert '"2026-03-15"' in serialised, "date must be serialised as ISO string"
    # Verify round-trip values
    assert payload["amount"] == "9.99"
    assert payload["date"] == "2026-03-15"
    assert payload["merchant"] == "Starbucks"
    assert payload["notes"] is None


def test_to_jsonable_month_summary_result_round_trips() -> None:
    """MonthSummaryResult with nested CurrencyMonthSummary + CategoryAmount must serialise."""
    import json

    cat = CategoryAmount(
        category="Food",
        amount=Decimal("123.45"),
        currency="USD",
        pct_of_expenses=0.6,
    )
    summary = CurrencyMonthSummary(
        currency="USD",
        total_income=Decimal("1000.00"),
        total_expenses=Decimal("400.00"),
        net_savings=Decimal("600.00"),
        savings_rate=0.6,
        top_categories=[cat],
        transaction_count=5,
    )
    result = MonthSummaryResult(year=2026, month=5, by_currency=[summary])

    payload = to_jsonable(result)
    serialised = json.dumps(payload)  # must not raise
    assert '"1000.00"' in serialised
    assert '"123.45"' in serialised


def test_to_jsonable_category_trend_result_round_trips() -> None:
    """CategoryTrendResult with Decimal amount must serialise correctly."""
    import json

    point = CategoryTrendPoint(year=2026, month=3, currency="USD", amount=Decimal("75.00"))
    result = CategoryTrendResult(category="Food", series=[point])

    payload = to_jsonable(result)
    serialised = json.dumps(payload)  # must not raise
    assert payload["series"][0]["amount"] == "75.00"
    assert '"75.00"' in serialised


def test_to_jsonable_spend_window_result_round_trips() -> None:
    """SpendWindowResult (has date fields) must serialise correctly."""
    import json

    result = SpendWindowResult(
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 30),
        by_currency=[],
    )
    payload = to_jsonable(result)
    serialised = json.dumps(payload)  # must not raise
    assert payload["start_date"] == "2026-04-01"
    assert payload["end_date"] == "2026-04-30"
    assert '"2026-04-01"' in serialised


# ---------------------------------------------------------------------------
# CategoryInfo / ListCategoriesResult — new dataclasses (Task 2)
# ---------------------------------------------------------------------------


def test_category_info_is_frozen() -> None:
    """CategoryInfo must be a frozen dataclass."""
    from dataclasses import FrozenInstanceError

    info = CategoryInfo(name="Food & Dining", category_type="expense", transaction_count=12)
    with pytest.raises(FrozenInstanceError):
        info.name = "other"  # type: ignore[misc]


def test_list_categories_result_is_frozen() -> None:
    """ListCategoriesResult must be a frozen dataclass."""
    from dataclasses import FrozenInstanceError

    result = ListCategoriesResult(categories=[])
    with pytest.raises(FrozenInstanceError):
        result.categories = []  # type: ignore[misc]


def test_category_info_fields() -> None:
    info = CategoryInfo(name="Transport", category_type="expense", transaction_count=5)
    assert info.name == "Transport"
    assert info.category_type == "expense"
    assert info.transaction_count == 5


def test_to_jsonable_list_categories_result_round_trips() -> None:
    """ListCategoriesResult must serialise via to_jsonable without error."""
    import json

    result = ListCategoriesResult(
        categories=[
            CategoryInfo(name="Food & Dining", category_type="expense", transaction_count=30),
            CategoryInfo(name="Salary", category_type="income", transaction_count=3),
        ]
    )
    payload = to_jsonable(result)
    serialised = json.dumps(payload)  # must not raise
    cats = payload["categories"]
    assert len(cats) == 2
    assert cats[0]["name"] == "Food & Dining"
    assert cats[0]["category_type"] == "expense"
    assert cats[0]["transaction_count"] == 30
    assert '"Food & Dining"' in serialised


def test_fake_chat_tools_satisfies_protocol_with_list_categories() -> None:
    """FakeChatTools with list_categories must satisfy the ChatTools Protocol."""

    class FullFakeChatTools:
        async def get_month_summary(
            self, user_id: str, year: int, month: int
        ) -> MonthSummaryResult:
            return MonthSummaryResult(year=year, month=month, by_currency=[])

        async def get_category_trend(
            self, user_id: str, category: str, n_months: int
        ) -> CategoryTrendResult:
            return CategoryTrendResult(category=category, series=[])

        async def get_spend_window(
            self, user_id: str, start_date: date, end_date: date
        ) -> SpendWindowResult:
            return SpendWindowResult(start_date=start_date, end_date=end_date, by_currency=[])

        async def get_user_profile(self, user_id: str) -> UserProfileResult:
            return UserProfileResult(months_covered=0, by_currency=[])

        async def search_transactions(
            self, user_id: str, text: str, limit: int
        ) -> SearchTransactionsResult:
            return SearchTransactionsResult(query=text, matches=[])

        async def list_categories(self, user_id: str) -> ListCategoriesResult:
            return ListCategoriesResult(categories=[])

    fake = FullFakeChatTools()
    assert isinstance(fake, ChatTools)
