"use client"
import { Suspense } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import Link from "next/link"
import { PageHead } from "@/components/shell/PageHead"
import { Button } from "@/components/ui/button"
import { InsightCTA } from "./InsightCTA"
import { TransactionList } from "@/features/transactions/components/TransactionList"
import { formatAmount } from "@/lib/utils"
import { useTransactions } from "@/features/transactions/hooks/useTransactions"
import { useUIStore } from "@/lib/store/ui"
import { useSummary } from "../hooks/useReports"
import { TrendChart } from "./TrendChart"
import type { components } from "@/lib/api/schema"

type TransactionItem = components["schemas"]["TransactionListItem"]

function DashboardViewInner() {
  const sp = useSearchParams()
  const router = useRouter()
  const now = new Date()

  const monthParam = sp.get("month")
  let year = now.getFullYear()
  let month = now.getMonth() + 1
  if (monthParam) {
    const [y, m] = monthParam.split("-").map(Number)
    if (
      Number.isInteger(y) && Number.isInteger(m) &&
      y >= 1970 && y <= 9999 &&
      m >= 1 && m <= 12
    ) { year = y; month = m }
  }

  const periodLabel = new Date(year, month - 1).toLocaleString("default", { month: "long", year: "numeric" })

  const { data: summaryData } = useSummary(year, month)
  const { data: recentData, isLoading } = useTransactions({ limit: 5 })
  const { openAdd } = useUIStore()

  const recentItems: TransactionItem[] = recentData?.items ?? []
  const isFirstTime = !isLoading && recentItems.length === 0
  const chartCurrency =
    summaryData?.expenses[0]?.currency ?? summaryData?.income[0]?.currency ?? "JPY"

  function navigate(delta: number) {
    const d = new Date(year, month - 1 + delta, 1)
    const p = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
    router.push(`/dashboard?month=${p}`)
  }

  return (
    <div>
      <PageHead crumb="DASHBOARD" title={periodLabel} />

      {/* Month navigation */}
      <div className="flex items-center gap-6 mb-8">
        <button onClick={() => navigate(-1)} className="font-mono text-base text-[var(--text-2)] hover:text-[var(--text)] transition-colors">←</button>
        <span className="font-sans text-sm text-[var(--text-2)]">{periodLabel}</span>
        <button onClick={() => navigate(1)} className="font-mono text-base text-[var(--text-2)] hover:text-[var(--text)] transition-colors">→</button>
      </div>

      {/* First-time onboarding — full takeover */}
      {isFirstTime && (
        <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] p-10 mb-8 text-center">
          <p className="font-serif text-2xl text-[var(--text)] mb-3">Welcome to Yomochi.</p>
          <p className="text-sm text-[var(--text-2)] max-w-[52ch] mx-auto mb-6 leading-relaxed">
            Add at least <strong className="text-[var(--text)]">5 transactions</strong> to unlock AI Insights —
            short monthly commentary based on your own history. Multi-currency, no FX conversion, no bank
            integrations.
          </p>
          <div className="flex items-center justify-center gap-3">
            <Button onClick={openAdd} className="bg-[var(--accent)] text-[var(--fab-fg)]">
              + Add first transaction
            </Button>
            <Link
              href="/transactions"
              className="font-mono text-xs uppercase tracking-widest text-[var(--text-3)] hover:text-[var(--text)]"
            >
              go to ledger →
            </Link>
          </div>
        </div>
      )}

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-[1fr_1fr_2fr] gap-4 mb-8">
        <div className="p-5 rounded-[var(--radius-lg)] bg-[var(--surface)] shadow-sm border-t-2 border-t-[var(--danger)]">
          <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-2">Expenses</p>
          {summaryData ? (
            summaryData.expenses.length > 0 ? (
              summaryData.expenses.map((e) => (
                <p key={e.currency} className="font-mono text-3xl text-[var(--text)]">
                  <span className="text-xs text-[var(--text-3)]">{e.currency} </span>{formatAmount(e.total)}
                </p>
              ))
            ) : (
              <p className="font-mono text-3xl text-[var(--text-3)]">—</p>
            )
          ) : (
            <div className="h-9 bg-[var(--rule)] rounded animate-pulse" />
          )}
        </div>
        <div className="p-5 rounded-[var(--radius-lg)] bg-[var(--surface)] shadow-sm border-t-2 border-t-[var(--income)]">
          <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-2">Income</p>
          {summaryData ? (
            summaryData.income.length > 0 ? (
              summaryData.income.map((e) => (
                <p key={e.currency} className="font-mono text-3xl text-[var(--income)]">
                  <span className="text-xs text-[var(--text-3)]">{e.currency} </span>{formatAmount(e.total)}
                </p>
              ))
            ) : (
              <p className="font-mono text-3xl text-[var(--text-3)]">—</p>
            )
          ) : (
            <div className="h-9 bg-[var(--rule)] rounded animate-pulse" />
          )}
        </div>
        <div className="sm:col-span-2 md:col-span-1">
          <TrendChart currency={chartCurrency} />
        </div>
      </div>

      <InsightCTA year={year} month={month} />

      {/* Recent transactions */}
      <div className="mt-8">
        <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-4">Recent</p>
        {isLoading ? (
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-14 bg-[var(--surface)] rounded animate-pulse" />
            ))}
          </div>
        ) : (
          <TransactionList transactions={recentItems} />
        )}
      </div>
    </div>
  )
}

export function DashboardView() {
  return (
    <Suspense fallback={
      <div className="space-y-4 p-4">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-24 bg-[var(--surface)] rounded animate-pulse" />
        ))}
      </div>
    }>
      <DashboardViewInner />
    </Suspense>
  )
}
