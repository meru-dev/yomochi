"""ChatTools port — typed tool library for function-calling chat backend.

Each method is user_id-scoped and returns typed dataclasses.  Field types are
*domain-accurate* (Decimal for amounts, date for dates) — they are NOT directly
passable to json.dumps.  Callers that need to serialise results (e.g. OpenAI
tool-role messages) must first convert via ``to_jsonable(result)``.
No OpenAI wiring lives here.
"""

import dataclasses
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class ToolName(StrEnum):
    GET_MONTH_SUMMARY = "get_month_summary"
    GET_CATEGORY_TREND = "get_category_trend"
    GET_SPEND_WINDOW = "get_spend_window"
    GET_USER_PROFILE = "get_user_profile"
    SEARCH_TRANSACTIONS = "search_transactions"
    LIST_CATEGORIES = "list_categories"


@dataclass(frozen=True)
class CategoryAmount:
    category: str
    amount: Decimal
    currency: str
    pct_of_expenses: float


@dataclass(frozen=True)
class CurrencyMonthSummary:
    currency: str
    total_income: Decimal
    total_expenses: Decimal
    net_savings: Decimal
    savings_rate: float
    top_categories: list[CategoryAmount]
    transaction_count: int


@dataclass(frozen=True)
class MonthSummaryResult:
    year: int
    month: int
    by_currency: list[CurrencyMonthSummary]


@dataclass(frozen=True)
class CategoryTrendPoint:
    year: int
    month: int
    currency: str
    amount: Decimal


@dataclass(frozen=True)
class CategoryTrendResult:
    category: str
    series: list[CategoryTrendPoint]


@dataclass(frozen=True)
class SpendWindowResult:
    start_date: date
    end_date: date
    by_currency: list[CurrencyMonthSummary]


@dataclass(frozen=True)
class UserProfileResult:
    months_covered: int
    by_currency: list[CurrencyMonthSummary]


@dataclass(frozen=True)
class TransactionMatch:
    transaction_id: str
    date: date
    amount: Decimal
    currency: str
    type_: str
    merchant: str | None
    notes: str | None
    category: str | None


@dataclass(frozen=True)
class SearchTransactionsResult:
    query: str
    matches: list[TransactionMatch]


@dataclass(frozen=True)
class CategoryInfo:
    name: str
    category_type: str
    transaction_count: int


@dataclass(frozen=True)
class ListCategoriesResult:
    categories: list[CategoryInfo]


@runtime_checkable
class ChatTools(Protocol):
    async def get_month_summary(
        self,
        user_id: str,
        year: int,
        month: int,
    ) -> MonthSummaryResult: ...

    async def get_category_trend(
        self,
        user_id: str,
        category: str,
        n_months: int,
    ) -> CategoryTrendResult:
        """Month-over-month EXPENSE series for one named category (n_months back from today).

        V1 constraint: only EXPENSE transactions are included.  If the category
        is used exclusively for income, the returned series will be empty.
        """
        ...

    async def get_spend_window(
        self,
        user_id: str,
        start_date: date,
        end_date: date,
    ) -> SpendWindowResult: ...

    async def get_user_profile(
        self,
        user_id: str,
    ) -> UserProfileResult:
        """4-month rolling aggregate — the live equivalent of the old portrait chunk."""
        ...

    async def search_transactions(
        self,
        user_id: str,
        text: str,
        limit: int,
    ) -> SearchTransactionsResult:
        """Fuzzy match on merchant/notes via pg_trgm (ILIKE) — user_id-scoped."""
        ...

    async def list_categories(
        self,
        user_id: str,
    ) -> ListCategoriesResult:
        """Distinct categories used by this user, ordered by transaction_count desc.

        Returns every category name the user has assigned to at least one
        transaction.  Each entry includes the category type (expense/income) and
        the user's transaction_count for that category so the model can prefer
        the most-used categories.  Use this to discover exact category names
        before calling get_category_trend or any category-filtered tool.
        """
        ...


# ---------------------------------------------------------------------------
# JSON serialisation helper
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """Recursively convert a ChatTools result to a json.dumps-compatible structure.

    Rules:
    - ``Decimal``  → ``str``  (preserves precision; do NOT convert to float)
    - ``date``     → ISO-8601 string via ``.isoformat()``
    - frozen dataclass → ``dict`` (fields recursively converted)
    - ``list``     → ``list`` (items recursively converted)
    - All other types are returned as-is (str, int, float, bool, None).

    Usage::

        import json
        from app.application.chat.ports.chat_tools import to_jsonable

        payload = json.dumps(to_jsonable(result))
    """
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, list):
        return [to_jsonable(item) for item in obj]
    return obj
