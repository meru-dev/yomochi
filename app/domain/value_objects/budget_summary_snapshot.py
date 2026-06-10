from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


class _BudgetRow(Protocol):
    amount: Decimal
    currency: str
    type_: str  # "income" | "expense"


@dataclass(frozen=True, slots=True)
class CurrencyTotals:
    currency: str
    income: Decimal
    expense: Decimal
    count: int


@dataclass(frozen=True, slots=True)
class BudgetSummarySnapshot:
    """Per-currency totals frozen at the moment an Insight is generated.

    No FX conversion, no unified totals across currencies.
    """

    per_currency: tuple[CurrencyTotals, ...]

    def to_json(self) -> list[dict[str, Any]]:
        return [
            {
                "currency": ct.currency,
                "income": str(ct.income),
                "expense": str(ct.expense),
                "count": ct.count,
            }
            for ct in self.per_currency
        ]

    @classmethod
    def from_json(cls, raw: list[dict[str, Any]] | None) -> "BudgetSummarySnapshot | None":
        if not raw:
            return None
        return cls(
            per_currency=tuple(
                CurrencyTotals(
                    currency=item["currency"],
                    income=Decimal(str(item["income"])),
                    expense=Decimal(str(item["expense"])),
                    count=int(item["count"]),
                )
                for item in raw
            )
        )

    @classmethod
    def aggregate_rows(cls, rows: Iterable[_BudgetRow]) -> "BudgetSummarySnapshot | None":
        """Group per-currency totals from a row sequence carrying (amount, currency, type_).

        Returns None for empty input so callers can distinguish "period had no
        Transactions" from "period had zero net flow".
        """
        income_by_ccy: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        expense_by_ccy: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        count_by_ccy: dict[str, int] = defaultdict(int)
        seen = False
        for r in rows:
            seen = True
            count_by_ccy[r.currency] += 1
            if r.type_ == "income":
                income_by_ccy[r.currency] += r.amount
            else:
                expense_by_ccy[r.currency] += r.amount
        if not seen:
            return None
        totals = tuple(
            CurrencyTotals(
                currency=ccy,
                income=income_by_ccy[ccy],
                expense=expense_by_ccy[ccy],
                count=count_by_ccy[ccy],
            )
            for ccy in sorted(count_by_ccy.keys())
        )
        return cls(per_currency=totals)
