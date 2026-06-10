from dataclasses import dataclass
from decimal import Decimal
from statistics import mean
from typing import Any

from app.domain.services.monthly_aggregator import MonthlyAggregation

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


@dataclass(frozen=True)
class ShiftThresholds:
    income_drop_high: float = 0.20
    income_drop_medium: float = 0.10
    expense_spike_high: float = 0.30
    expense_spike_medium: float = 0.15
    savings_rate_collapse: float = 0.15
    savings_rate_decline: float = 0.08
    category_spike_high: float = 0.40
    category_spike_medium: float = 0.20


@dataclass(frozen=True)
class DetectedShift:
    type: str  # income_drop | expense_spike | savings_collapse | savings_decline | category_spike
    severity: str  # high | medium
    delta_pct: float
    category: str | None = None
    currency: str = ""
    abs_change: Decimal = Decimal("0")

    def to_metadata(self) -> dict[str, Any]:
        return {
            "shift_type": self.type,
            "severity": self.severity,
            "delta_pct": self.delta_pct,
            "category": self.category,
            "currency": self.currency,
            "abs_change": str(self.abs_change),
        }


def _avg_categories(history: list[MonthlyAggregation]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    counts: dict[str, int] = {}
    for agg in history:
        for cat, amt, _ in agg.top_categories:
            totals[cat] = totals.get(cat, Decimal("0")) + amt
            counts[cat] = counts.get(cat, 0) + 1
    return {cat: totals[cat] / counts[cat] for cat in totals}


def format_shift_text(current: MonthlyAggregation, shifts: list[DetectedShift]) -> str:
    if not shifts:
        return ""
    month_name = _MONTH_NAMES[current.month]
    lines = [f"Behavioral shift detected in {month_name} {current.year}:"]
    for s in shifts:
        delta_str = f"{abs(s.delta_pct) * 100:.1f}%"
        if s.type == "income_drop":
            lines.append(f"- Income dropped by {delta_str} ({s.severity} severity).")
        elif s.type == "expense_spike":
            lines.append(f"- Expenses spiked by {delta_str} ({s.severity} severity).")
        elif s.type == "savings_collapse":
            lines.append(f"- Savings rate collapsed by {delta_str} ({s.severity} severity).")
        elif s.type == "savings_decline":
            lines.append(f"- Savings rate declined by {delta_str} ({s.severity} severity).")
        elif s.type == "category_spike" and s.category:
            lines.append(
                f"- Spending on '{s.category}' spiked by {delta_str} ({s.severity} severity)."
            )
    return "\n".join(lines)


class BehavioralShiftDetector:
    def __init__(self, thresholds: ShiftThresholds | None = None) -> None:
        self._t = thresholds or ShiftThresholds()

    def detect(
        self,
        current: MonthlyAggregation,
        history: list[MonthlyAggregation],
    ) -> list[DetectedShift]:
        if len(history) < 2:
            return []

        t = self._t
        shifts: list[DetectedShift] = []

        avg_income = Decimal(str(mean(float(h.total_income) for h in history)))
        avg_expenses = Decimal(str(mean(float(h.total_expenses) for h in history)))
        avg_savings_rate = mean(h.savings_rate for h in history)
        avg_categories = _avg_categories(history)

        if avg_income > 0:
            income_delta = float((current.total_income - avg_income) / avg_income)
            if income_delta < -t.income_drop_high:
                shifts.append(
                    DetectedShift(
                        type="income_drop",
                        severity="high",
                        delta_pct=income_delta,
                        currency=current.currency,
                        abs_change=abs(current.total_income - avg_income),
                    )
                )
            elif income_delta < -t.income_drop_medium:
                shifts.append(
                    DetectedShift(
                        type="income_drop",
                        severity="medium",
                        delta_pct=income_delta,
                        currency=current.currency,
                        abs_change=abs(current.total_income - avg_income),
                    )
                )

        if avg_expenses > 0:
            expense_delta = float((current.total_expenses - avg_expenses) / avg_expenses)
            if expense_delta > t.expense_spike_high:
                shifts.append(
                    DetectedShift(
                        type="expense_spike",
                        severity="high",
                        delta_pct=expense_delta,
                        currency=current.currency,
                        abs_change=abs(current.total_expenses - avg_expenses),
                    )
                )
            elif expense_delta > t.expense_spike_medium:
                shifts.append(
                    DetectedShift(
                        type="expense_spike",
                        severity="medium",
                        delta_pct=expense_delta,
                        currency=current.currency,
                        abs_change=abs(current.total_expenses - avg_expenses),
                    )
                )

        savings_delta = avg_savings_rate - current.savings_rate
        if savings_delta > t.savings_rate_collapse:
            shifts.append(
                DetectedShift(
                    type="savings_collapse",
                    severity="high",
                    delta_pct=-savings_delta,
                    currency=current.currency,
                    abs_change=Decimal(str(abs(savings_delta))) * avg_expenses,
                )
            )
        elif savings_delta > t.savings_rate_decline:
            shifts.append(
                DetectedShift(
                    type="savings_decline",
                    severity="medium",
                    delta_pct=-savings_delta,
                    currency=current.currency,
                    abs_change=Decimal(str(abs(savings_delta))) * avg_expenses,
                )
            )

        for cat, current_amt, _ in current.top_categories:
            if cat in avg_categories and avg_categories[cat] > 0:
                cat_delta = float((current_amt - avg_categories[cat]) / avg_categories[cat])
                if cat_delta > t.category_spike_high:
                    shifts.append(
                        DetectedShift(
                            type="category_spike",
                            severity="high",
                            delta_pct=cat_delta,
                            category=cat,
                            currency=current.currency,
                            abs_change=abs(current_amt - avg_categories[cat]),
                        )
                    )
                elif cat_delta > t.category_spike_medium:
                    shifts.append(
                        DetectedShift(
                            type="category_spike",
                            severity="medium",
                            delta_pct=cat_delta,
                            category=cat,
                            currency=current.currency,
                            abs_change=abs(current_amt - avg_categories[cat]),
                        )
                    )

        return shifts
