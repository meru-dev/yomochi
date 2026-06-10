"use client"
import type { components } from "@/lib/api/schema"
import { formatAmount } from "@/lib/utils"

type CurrencyTotals = components["schemas"]["CurrencyTotalsResponse"]
type CurrencyTotal = components["schemas"]["CurrencyTotal"]

interface Cell {
  currency: string
  income: number
  expense: number
  count: number
  isSnapshot: boolean
}

interface Props {
  budgetSummary: CurrencyTotals[] | null | undefined
  expenses: CurrencyTotal[] | undefined
  income: CurrencyTotal[] | undefined
  prevExpenses: CurrencyTotal[] | undefined
  prevYear: number
  prevMonth: number
}

export function CurrencySummaryGrid({
  budgetSummary,
  expenses,
  income,
  prevExpenses,
  prevYear,
  prevMonth,
}: Props) {
  let cells: Cell[] = []

  if (Array.isArray(budgetSummary) && budgetSummary.length > 0) {
    cells = budgetSummary.map((b) => ({
      currency: b.currency,
      income: parseFloat(b.income),
      expense: parseFloat(b.expense),
      count: b.count,
      isSnapshot: true,
    }))
  } else if (expenses?.length || income?.length) {
    const byCcy = new Map<string, Cell>()
    for (const e of expenses ?? []) {
      const c = byCcy.get(e.currency) ?? { currency: e.currency, income: 0, expense: 0, count: 0, isSnapshot: false }
      c.expense = parseFloat(e.total)
      c.count += e.count
      byCcy.set(e.currency, c)
    }
    for (const e of income ?? []) {
      const c = byCcy.get(e.currency) ?? { currency: e.currency, income: 0, expense: 0, count: 0, isSnapshot: false }
      c.income = parseFloat(e.total)
      c.count += e.count
      byCcy.set(e.currency, c)
    }
    cells = Array.from(byCcy.values())
  }

  if (cells.length === 0) return null

  const prevExpMap = new Map<string, number>(
    (prevExpenses ?? []).map((e) => [e.currency, parseFloat(e.total)])
  )

  return (
    <div className="border-t border-[var(--rule)] pt-4">
      <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-3">
        Period totals · per currency
        {!cells[0].isSnapshot && (
          <span className="ml-2 normal-case text-[var(--text-3)]" title="No snapshot — showing live values">
            (live)
          </span>
        )}
      </p>
      <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))" }}>
        {cells.map((c) => {
          const prevExp = prevExpMap.get(c.currency)
          const delta =
            prevExp && prevExp > 0 && c.expense > 0
              ? ((c.expense - prevExp) / prevExp) * 100
              : null
          return (
            <div key={c.currency} className="px-3 py-2 rounded-[var(--radius-sm)] bg-[var(--surface)]">
              <p className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-3)] mb-1">
                {c.currency} · {c.count} tx
              </p>
              {c.expense > 0 && (
                <p className="font-mono text-base text-[var(--text)]">
                  <span className="text-[10px] text-[var(--text-3)] mr-1">expense</span>
                  {formatAmount(c.expense.toString())}
                  {delta !== null && (
                    <span
                      className={`ml-2 text-[11px] ${delta > 0 ? "text-[var(--danger)]" : "text-[var(--income)]"}`}
                      title={`vs ${prevYear}-${String(prevMonth).padStart(2, "0")} (live)`}
                    >
                      {delta > 0 ? "+" : ""}{delta.toFixed(1)}%
                    </span>
                  )}
                </p>
              )}
              {c.income > 0 && (
                <p className="font-mono text-base text-[var(--income)]">
                  <span className="text-[10px] text-[var(--text-3)] mr-1">income</span>
                  {formatAmount(c.income.toString())}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
