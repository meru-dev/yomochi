"use client"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { ChevronDown } from "lucide-react"
import { useInsightsList, type InsightItem } from "../hooks/useInsightsList"
import { PageHead } from "@/components/shell/PageHead"

function periodLabel(item: InsightItem): string {
  const d = new Date(item.period_year, item.period_month - 1, 1)
  if (item.period === "weekly") {
    return `Week of ${d.toLocaleString("default", { month: "short", day: "numeric" })}, ${item.period_year}`
  }
  return d.toLocaleString("default", { month: "long", year: "numeric" })
}

function periodHref(item: InsightItem): string {
  const p = `${item.period_year}-${String(item.period_month).padStart(2, "0")}`
  return `/insights/${item.period}/${p}`
}

function ContextBadge({ q }: { q: string | null }) {
  if (!q) return null
  const label =
    q === "full" ? "full context"
    : q === "partial" ? "partial context"
    : "no history"
  const cls =
    q === "full" ? "bg-[var(--ok)] text-[var(--fab-fg)]"
    : q === "partial" ? "bg-[var(--warn)] text-[var(--fab-fg)]"
    : "bg-[var(--danger)] text-white"
  return (
    <span className={`font-mono text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded-[var(--radius-sm)] ${cls}`}>
      {label}
    </span>
  )
}

function StatusBadge({ s }: { s: string }) {
  if (s === "completed") return null
  const cls =
    s === "failed" ? "text-[var(--danger)] border-[var(--danger)]"
    : "text-[var(--warn)] border-[var(--warn)]"
  return (
    <span className={`font-mono text-[10px] uppercase tracking-widest px-1.5 py-0.5 rounded-[var(--radius-sm)] border ${cls}`}>
      {s}
    </span>
  )
}

function buildRecentMonths(n: number): { year: number; month: number; label: string; href: string }[] {
  const now = new Date()
  return Array.from({ length: n }, (_, i) => {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    const year = d.getFullYear()
    const month = d.getMonth() + 1
    const pad = String(month).padStart(2, "0")
    return {
      year,
      month,
      label: d.toLocaleString("default", { month: "long", year: "numeric" }),
      href: `/insights/monthly/${year}-${pad}`,
    }
  })
}

export function InsightsIndexPage() {
  const router = useRouter()
  const { data: insights, isLoading, isError } = useInsightsList(50)

  const recentMonths = buildRecentMonths(12)

  const existingPeriods = new Set(
    (insights ?? []).map((i) => `${i.period_year}-${String(i.period_month).padStart(2, "0")}`)
  )

  function handlePeriodSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    if (e.target.value) router.push(e.target.value)
  }

  const now = new Date()
  const thisYear = now.getFullYear()
  const thisMonth = now.getMonth() + 1
  const thisPeriod = `${thisYear}-${String(thisMonth).padStart(2, "0")}`

  return (
    <div>
      <PageHead crumb="INSIGHTS" title="Insights" />

      <div className="flex items-center gap-3 mb-8">
        <div className="relative inline-flex items-center">
          <select
            onChange={handlePeriodSelect}
            defaultValue=""
            className="pl-3 pr-8 py-1.5 bg-[var(--accent)] text-[var(--fab-fg)] font-mono text-xs uppercase tracking-widest rounded-[var(--radius-sm)] cursor-pointer hover:opacity-80 transition-opacity appearance-none"
          >
            <option value="" disabled>+ New insight</option>
            {recentMonths.map(({ year, month, label, href }) => {
              const key = `${year}-${String(month).padStart(2, "0")}`
              const hasInsight = existingPeriods.has(key)
              return (
                <option key={key} value={href} className="normal-case">
                  {label}{hasInsight ? " ✓" : ""}
                </option>
              )
            })}
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--fab-fg)] pointer-events-none" />
        </div>
        <Link
          href={`/insights/weekly/${thisPeriod}`}
          className="inline-flex items-center px-3 py-1.5 border border-[var(--rule-strong)] text-[var(--text-2)] font-mono text-xs uppercase tracking-widest rounded-[var(--radius-sm)] hover:text-[var(--text)]"
        >
          weekly
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-16 rounded-[var(--radius-md)] bg-[var(--surface)] animate-pulse" />
          ))}
        </div>
      ) : isError ? (
        <p className="text-[var(--danger)] font-mono text-sm">Failed to load insights.</p>
      ) : !insights || insights.length === 0 ? (
        <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] p-8 text-center">
          <p className="font-serif text-lg text-[var(--text)] mb-2">No insights yet.</p>
          <p className="text-sm text-[var(--text-2)] max-w-[44ch] mx-auto mb-5">
            Add at least 5 transactions in a period, then pick a month above to generate an AI-written insight.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {insights.map((i) => (
            <li key={i.id}>
              <Link
                href={periodHref(i)}
                className="flex items-center justify-between gap-4 p-4 rounded-[var(--radius-md)] bg-[var(--surface)] hover:bg-[var(--surface-2,var(--surface))] transition-colors group"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-3)]">
                      {i.period} · {periodLabel(i)}
                    </span>
                    <ContextBadge q={i.context_quality} />
                    <StatusBadge s={i.status} />
                  </div>
                  <p className="font-serif text-base text-[var(--text)] truncate group-hover:text-[var(--accent)] transition-colors">
                    {i.title ?? (i.status === "completed" ? "(no title)" : "Pending generation")}
                  </p>
                </div>
                {i.impact_score !== null && (
                  <div className="text-right shrink-0">
                    <span className="font-mono text-3xl text-[var(--accent)] leading-none tracking-[-0.03em]">
                      {i.impact_score}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--text-3)] ml-0.5">/10</span>
                  </div>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
