import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from statistics import mean, pstdev


@dataclass(frozen=True)
class MonthlyAggregation:
    year: int
    month: int
    currency: str
    total_income: Decimal
    total_expenses: Decimal
    net_savings: Decimal
    savings_rate: float
    expense_volatility: float
    top_categories: list[tuple[str, Decimal, float]]  # (label, amount, pct_of_expenses)
    transaction_count: int
    avg_transaction_amount: Decimal
    income_sources_count: int
    largest_single_expense: Decimal


_MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _bucket(value: float | Decimal, relative: float = 0.05) -> int:
    abs_val = abs(float(value))
    if abs_val == 0:
        return 0
    step = max(1, int(abs_val * relative))
    return int(float(value) / step) * step


def compute_semantic_hash(aggs: list[MonthlyAggregation], bucket_pct: float = 0.05) -> str:
    if not aggs:
        return ""
    per_currency = []
    for agg in aggs:
        per_currency.append(
            {
                "currency": agg.currency,
                "income_bucket": _bucket(agg.total_income, bucket_pct),
                "expenses_bucket": _bucket(agg.total_expenses, bucket_pct),
                "savings_rate_bucket": _bucket(agg.savings_rate, bucket_pct),
                "top_categories": [
                    (cat, _bucket(amt, bucket_pct), _bucket(pct, bucket_pct))
                    for cat, amt, pct in agg.top_categories[:5]
                ],
                "volatility_high": agg.expense_volatility > 0.3,
            }
        )
    content = json.dumps(per_currency, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def format_monthly_summary(aggs: list[MonthlyAggregation]) -> str:
    if not aggs:
        return ""
    primary = aggs[0]
    month_name = _MONTH_NAMES[primary.month]

    income_parts = ", ".join(f"{a.total_income:.0f} {a.currency}" for a in aggs)
    expenses_parts = ", ".join(f"{a.total_expenses:.0f} {a.currency}" for a in aggs)
    savings_parts = ", ".join(f"{a.net_savings:.0f} {a.currency}" for a in aggs)

    if primary.expense_volatility < 0.15:
        volatility_label = "low"
    elif primary.expense_volatility < 0.30:
        volatility_label = "moderate"
    else:
        volatility_label = "high"

    savings_rate_pct = round(primary.savings_rate * 100, 1)

    category_sections = []
    for a in aggs:
        lines = "\n".join(
            f"- {cat}: {amt:.0f} {a.currency} ({pct * 100:.1f}% of expenses)"
            for cat, amt, pct in a.top_categories[:5]
        )
        if len(aggs) > 1:
            category_sections.append(f"[{a.currency}]\n{lines}")
        else:
            category_sections.append(lines)
    categories_text = "\n".join(category_sections)

    return (
        f"Monthly financial summary: {month_name} {primary.year}.\n\n"
        f"Income: {income_parts} | "
        f"Expenses: {expenses_parts} | "
        f"Savings: {savings_parts} ({savings_rate_pct}% rate).\n"
        f"Transactions: {primary.transaction_count} | "
        f"Avg transaction: {primary.avg_transaction_amount:.1f} {primary.currency}.\n"
        f"Largest single expense: {primary.largest_single_expense:.0f} {primary.currency}.\n\n"
        f"Spending breakdown:\n{categories_text}\n\n"
        f"Expense volatility: {volatility_label}.\n"
        f"Income sources: {primary.income_sources_count}."
    )


@dataclass(frozen=True)
class TransactionRow:
    """Raw transaction data passed by application layer to this domain service."""

    amount: Decimal
    currency: str
    type_: str  # "income" | "expense"
    category_label: str | None
    day_of_month: int


def aggregate(year: int, month: int, rows: list[TransactionRow]) -> list[MonthlyAggregation]:
    """Aggregate raw rows grouped by currency into MonthlyAggregation objects."""
    by_currency: dict[str, list[TransactionRow]] = {}
    for row in rows:
        by_currency.setdefault(row.currency, []).append(row)

    result = []
    for currency, txs in sorted(by_currency.items()):
        incomes = [t.amount for t in txs if t.type_ == "income"]
        expenses = [t.amount for t in txs if t.type_ == "expense"]

        total_income = sum(incomes, Decimal("0"))
        total_expenses = sum(expenses, Decimal("0"))
        net_savings = total_income - total_expenses
        savings_rate = float(net_savings / total_income) if total_income > 0 else 0.0

        # daily expense buckets for volatility
        daily: dict[int, Decimal] = {}
        for t in txs:
            if t.type_ == "expense":
                daily[t.day_of_month] = daily.get(t.day_of_month, Decimal("0")) + t.amount
        daily_vals = [float(v) for v in daily.values()]
        if len(daily_vals) >= 2:
            avg_daily = mean(daily_vals)
            expense_volatility = pstdev(daily_vals) / avg_daily if avg_daily > 0 else 0.0
        else:
            expense_volatility = 0.0

        # top categories
        cat_totals: dict[str, Decimal] = {}
        for t in txs:
            if t.type_ == "expense" and t.category_label:
                cat_totals[t.category_label] = (
                    cat_totals.get(t.category_label, Decimal("0")) + t.amount
                )
        top_cats: list[tuple[str, Decimal, float]] = []
        for cat, amt in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)[:5]:
            pct = float(amt / total_expenses) if total_expenses > 0 else 0.0
            top_cats.append((cat, amt, pct))

        avg_tx = (total_income + total_expenses) / len(txs) if txs else Decimal("0")
        income_sources = len(
            {t.category_label for t in txs if t.type_ == "income" and t.category_label}
        )
        largest_expense = max(expenses, default=Decimal("0"))

        result.append(
            MonthlyAggregation(
                year=year,
                month=month,
                currency=currency,
                total_income=total_income,
                total_expenses=total_expenses,
                net_savings=net_savings,
                savings_rate=savings_rate,
                expense_volatility=expense_volatility,
                top_categories=top_cats,
                transaction_count=len(txs),
                avg_transaction_amount=avg_tx,
                income_sources_count=income_sources,
                largest_single_expense=largest_expense,
            )
        )
    return result
