from decimal import Decimal

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
_SHIFT_THRESHOLD = 0.10


def compute_window_averages(
    months: list[list[MonthlyAggregation]],
) -> dict[str, dict[str, Decimal]]:
    """Average spend per category per currency across N baseline months.

    Returns: {currency: {category_label: avg_amount}}
    """
    sums: dict[str, dict[str, Decimal]] = {}
    month_counts: dict[str, int] = {}

    for month_aggs in months:
        seen = set()
        for agg in month_aggs:
            ccy = agg.currency
            if ccy not in seen:
                month_counts[ccy] = month_counts.get(ccy, 0) + 1
                seen.add(ccy)
            if ccy not in sums:
                sums[ccy] = {}
            for cat, amt, _ in agg.top_categories:
                sums[ccy][cat] = sums[ccy].get(cat, Decimal("0")) + amt

    return {
        ccy: {cat: amt / month_counts[ccy] for cat, amt in cats.items()}
        for ccy, cats in sums.items()
    }


def format_portrait_text(
    recent: list[MonthlyAggregation],
    baseline_months: list[list[MonthlyAggregation]],
) -> str:
    """Template-based portrait text. No LLM.

    Shows category shift only if abs(delta) >= 10% (noise filter).
    Multi-currency: one section per currency.
    """
    if not recent:
        return ""

    primary = recent[0]
    month_name = _MONTH_NAMES[primary.month]

    header = f"User financial portrait — {month_name} {primary.year}"
    non_empty = [m for m in baseline_months if m]
    if non_empty:
        start_agg = non_empty[0][0]
        end_agg = non_empty[-1][0]
        start_abbr = _MONTH_NAMES[start_agg.month][:3]
        end_abbr = _MONTH_NAMES[end_agg.month][:3]
        if start_agg.year == end_agg.year:
            bl_label = f"{start_abbr}–{end_abbr} {end_agg.year}"
        else:
            bl_label = f"{start_abbr} {start_agg.year}–{end_abbr} {end_agg.year}"
        header += f" vs {bl_label} baseline"

    window_avgs = compute_window_averages(baseline_months) if baseline_months else {}

    lines = [header, ""]

    for agg in recent:
        ccy = agg.currency
        avgs = window_avgs.get(ccy, {})

        lines.append(f"Spending ({ccy}):")
        for cat, amt, _ in agg.top_categories:
            bl = avgs.get(cat)
            if bl and bl > 0:
                delta = float((amt - bl) / bl)
                if abs(delta) >= _SHIFT_THRESHOLD:
                    sign = "↑" if delta > 0 else "↓"
                    pct = round(abs(delta) * 100)
                    lines.append(f"  {cat}: {amt:.0f} {ccy}  {sign}{pct}% from baseline {bl:.0f}")
                else:
                    lines.append(f"  {cat}: {amt:.0f} {ccy}  stable")
            else:
                lines.append(f"  {cat}: {amt:.0f} {ccy}")

        savings_pct = round(agg.savings_rate * 100)
        lines.append(
            f"\nTotal spend: {agg.total_expenses:.0f} {ccy} | "
            f"Transactions: {agg.transaction_count} | "
            f"Savings rate: {savings_pct}%"
        )

    return "\n".join(lines)
