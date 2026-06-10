"use client"
import { Suspense } from "react"
import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useInsightByPeriod, useRequestInsightForPage } from "../hooks/useInsight"
import { useSummary } from "@/features/dashboard/hooks/useReports"
import { Button } from "@/components/ui/button"
import { CurrencySummaryGrid } from "./CurrencySummaryGrid"

const SCOPE_TABS = ["monthly", "weekly"] as const

function getRequestErrorMessage(err: unknown): string {
  const code = (err as { error?: { code?: string } } | null)?.error?.code
  if (code === "insights.insufficient_transactions") return "Not enough data yet — add more transactions and try again."
  if (code === "quota.exceeded") return "Monthly insight quota reached. Try again next month."
  if (code === "auth.required") return "You must be logged in."
  if (code === "storage.error") return "A server error occurred. Please try again."
  return "Something went wrong. Please try again."
}

function InsightPageInner() {
  const params = useParams<{ scope: string; period: string }>()
  const router = useRouter()
  const [year, month] = params.period.split("-").map(Number)
  const { data: insight, isLoading, isError } = useInsightByPeriod(params.scope, year, month)
  const { data: summary } = useSummary(year, month)
  const prevMonth = month === 1 ? 12 : month - 1
  const prevYear = month === 1 ? year - 1 : year
  const { data: prevSummary } = useSummary(prevYear, prevMonth)
  const request = useRequestInsightForPage()

  function navigate(delta: number) {
    const d = new Date(year, month - 1 + delta, 1)
    if (d > new Date()) return
    const p = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`
    router.push(`/insights/${params.scope}/${p}`)
  }

  const periodLabel = new Date(year, month - 1).toLocaleString("default", {
    month: "long", year: "numeric",
  })

  return (
    <div>
      <div className="flex items-start justify-between mb-8">
        <div>
          <p className="font-mono text-[11px] text-[var(--text-3)] uppercase tracking-[0.04em] mb-1">
            <Link href="/insights" className="hover:text-[var(--text)] transition-colors">Insights</Link>
            <span className="mx-1 opacity-40">/</span>
            {periodLabel}
          </p>
          <h1 className="font-serif text-[clamp(26px,3vw,36px)] text-[var(--text)] leading-[1.15] tracking-[-0.005em]">
            Insight
          </h1>
          <Link
            href={`/chat?q=${encodeURIComponent(`Analyze my spending in ${periodLabel}`)}`}
            className="inline-flex items-center gap-1 text-xs text-[var(--text-3)] hover:text-[var(--accent)] transition-colors mt-2"
          >
            ✦ Ask AI about this period
          </Link>
        </div>
      </div>

      {/* Scope tabs */}
      <div className="flex gap-0 border-b border-[var(--rule)] mb-6">
        {SCOPE_TABS.map((s) => (
          <button key={s} onClick={() => router.push(`/insights/${s}/${params.period}`)}
            className={`px-4 py-2 text-sm capitalize transition-colors
              ${params.scope === s
                ? "border-b-2 border-[var(--accent)] text-[var(--text)]"
                : "text-[var(--text-3)] hover:text-[var(--text)]"}`}>
            {s}
          </button>
        ))}
      </div>

      {/* Period nav */}
      <div className="flex items-center justify-between mb-8">
        <button onClick={() => navigate(-1)} className="font-mono text-sm text-[var(--text-2)]">←</button>
        <span className="font-mono text-xs uppercase tracking-widest text-[var(--text-3)]">{periodLabel}</span>
        <button onClick={() => navigate(1)} className="font-mono text-sm text-[var(--text-2)]">→</button>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[88, 76, 60, 92].map((w, i) => (
            <div key={i} className="h-4 rounded bg-[var(--surface)] animate-pulse" style={{ width: `${w}%` }} />
          ))}
        </div>
      ) : isError ? (
        <p className="text-[var(--danger)] font-mono text-sm">Failed to load insight. Please try again.</p>
      ) : !insight || insight.status === "pending" ? (
        <div className="space-y-4">
          <p className="text-sm text-[var(--text-2)] max-w-[52ch]">
            No insight yet for {periodLabel}. Generate one to see a summary of your spending.
          </p>
          <Button onClick={() => request.mutate({ period: params.scope, period_year: year, period_month: month })}
            className="bg-[var(--accent)] text-[var(--fab-fg)]">
            Generate {params.scope} insight
          </Button>
          {request.isError && (
            <p className="text-[var(--danger)] text-sm font-mono">
              {getRequestErrorMessage(request.error)}
            </p>
          )}
        </div>
      ) : insight.status === "queued" || insight.status === "processing" ? (
        <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] shadow-sm p-8 space-y-4">
          <p className="font-sans text-xs uppercase tracking-widest text-[var(--warn)]">Processing</p>
          <p className="font-serif text-[22px] text-[var(--text)]">
            Analysing your {params.scope} data
            <span className="inline-flex gap-1 ml-2">
              {[0,1,2].map(i => (
                <span key={i} className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-pulse"
                  style={{ animationDelay: `${i * 180}ms` }} />
              ))}
            </span>
          </p>
          {[88, 78, 60, 96].map((w, i) => (
            <div key={i} className="h-3 rounded bg-[var(--surface)] overflow-hidden">
              <div className="h-full animate-pulse bg-[var(--rule-strong)]" style={{ width: `${w}%` }} />
            </div>
          ))}
        </div>
      ) : insight.status === "failed" ? (
        <div className="border border-[var(--danger)] rounded-[var(--radius-lg)] p-8 space-y-4">
          <p className="font-sans text-xs uppercase tracking-widest text-[var(--danger)]">Failed</p>
          <p className="font-serif text-xl text-[var(--text)]">Generation failed.</p>
          <Button onClick={() => request.mutate({ period: params.scope, period_year: year, period_month: month })}
            className="border border-[var(--danger)] text-[var(--danger)] bg-transparent">
            Retry
          </Button>
        </div>
      ) : (
        <div className="grid gap-8 lg:gap-14 grid-cols-1 lg:grid-cols-[1fr_220px]">
          <div className="space-y-6">
            {insight.context_quality && (
              <span
                title={
                  insight.context_quality === "full"
                    ? "FULL — at least 3 months of historical data backed this analysis. Highest confidence."
                    : insight.context_quality === "partial"
                    ? "PARTIAL — limited history (1–2 months). Patterns may not be representative yet."
                    : "NONE — first period of data. Treat observations as preliminary."
                }
                className={`inline-flex items-center gap-1 font-mono text-xs uppercase tracking-widest px-2 py-0.5 rounded-[var(--radius-sm)] cursor-help
                  ${insight.context_quality === "full" ? "bg-[var(--ok)] text-[var(--fab-fg)]"
                    : insight.context_quality === "partial" ? "bg-[var(--warn)] text-[var(--fab-fg)]"
                    : "bg-[var(--danger)] text-white"}`}
              >
                {insight.context_quality === "full" ? "Full context"
                  : insight.context_quality === "partial" ? "Partial context"
                  : "No history"}
                <span className="opacity-70 text-[10px]" aria-hidden="true">ⓘ</span>
              </span>
            )}
            {insight.partial_context_warning && (
              <div className="border-l-2 border-[var(--warn)] pl-4 py-2 text-sm text-[var(--text-2)]">
                Limited history available — insight quality may be reduced.
              </div>
            )}
            <h2 className="font-serif text-[clamp(22px,2.4vw,28px)] font-medium text-[var(--text)]">
              {insight.title}
            </h2>
            {insight.description && (
              <div className="font-serif text-base text-[var(--text)] leading-[1.65] max-w-[65ch] space-y-4">
                {insight.description.split("\n\n").map((para: string, i: number) => (
                  <p key={i}>{para}</p>
                ))}
              </div>
            )}

            <CurrencySummaryGrid
              budgetSummary={insight.budget_summary}
              expenses={summary?.expenses}
              income={summary?.income}
              prevExpenses={prevSummary?.expenses}
              prevYear={prevYear}
              prevMonth={prevMonth}
            />

            <div className="border-t border-[var(--rule)] pt-4 flex items-center gap-4">
              <span className="font-mono text-xs text-[var(--text-3)]">
                Generated {insight.generated_at ? new Date(insight.generated_at).toLocaleDateString() : "—"}
              </span>
              <button
                onClick={() => request.mutate({
                  period: params.scope,
                  period_year: year,
                  period_month: month,
                })}
                disabled={request.isPending}
                className="font-mono text-xs text-[var(--text-3)] hover:text-[var(--text)] transition-colors disabled:opacity-40"
                title="Generate a fresh insight for this period (uses one quota slot)"
              >
                {request.isPending ? "Refreshing…" : "Refresh insight"}
              </button>
              {request.isError && (
                <span className="font-mono text-xs text-[var(--danger)]">
                  {getRequestErrorMessage(request.error)}
                </span>
              )}
            </div>
          </div>

          {/* Meta sidebar */}
          <div className="space-y-6 lg:border-l lg:border-[var(--rule)] lg:pl-8">
            {insight.impact_score && (
              <div>
                <p
                  className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-1 cursor-help"
                  title="1–3: minor patterns · 4–6: moderate · 7–10: significant — higher scores warrant closer attention"
                >
                  Impact score ⓘ
                </p>
                <span className="font-mono text-[56px] text-[var(--accent)] leading-none tracking-[-0.03em]">
                  {insight.impact_score}
                </span>
                <span className="font-mono text-sm text-[var(--text-3)]">/10</span>
                <p className="font-mono text-[10px] text-[var(--text-3)] mt-1">
                  {insight.impact_score <= 3 ? "minor"
                    : insight.impact_score <= 6 ? "moderate"
                    : "significant"}
                </p>
              </div>
            )}
            <div>
              <p className="font-mono text-xs text-[var(--text-3)] uppercase tracking-widest">Scope</p>
              <p className="font-mono text-sm capitalize text-[var(--text-2)] mt-1">{params.scope}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function InsightPage() {
  return (
    <Suspense fallback={
      <div className="space-y-4 p-4">
        <div className="h-8 w-48 bg-[var(--surface)] rounded animate-pulse" />
        <div className="h-32 bg-[var(--surface)] rounded animate-pulse" />
      </div>
    }>
      <InsightPageInner />
    </Suspense>
  )
}
