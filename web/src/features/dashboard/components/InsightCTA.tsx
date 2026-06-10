"use client"
import { useLatestInsight } from "../hooks/useDashboardInsight"
import Link from "next/link"

export function InsightCTA({ year, month }: { year: number; month: number }) {
  const { data: insight, isLoading } = useLatestInsight(year, month)

  if (isLoading) return null

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const status = (insight as any)?.status

  return (
    <section className="border-y border-[var(--rule)] py-7">
      <p className="font-sans text-[11px] uppercase tracking-[0.18em] text-[var(--text-3)] mb-3">
        Monthly Insight
        {status === "completed" && " · ready"}
        {(status === "queued" || status === "processing") && " · processing"}
        {status === "failed" && " · failed"}
      </p>

      {!insight ? (
        <>
          <h2 className="font-serif text-[clamp(22px,2.4vw,28px)] font-medium text-[var(--text)] mb-2">
            See how your {new Date(year, month - 1).toLocaleString("default", { month: "long" })} looked
          </h2>
          <p className="text-sm text-[var(--text-2)] mb-4">
            Generate an AI-written summary of your spending this month.
          </p>
          <Link
            href="/insights"
            className="inline-flex items-center justify-center rounded-lg px-4 h-9 text-sm font-medium bg-[var(--accent)] text-[var(--fab-fg)] transition-opacity hover:opacity-80"
          >
            Go to Insights →
          </Link>
        </>
      ) : status === "queued" || status === "processing" ? (
        <div className="space-y-2">
          <p className="font-serif text-[22px] text-[var(--text)]">
            Analysing your transactions
            <span className="inline-flex gap-1 ml-2">
              {[0, 1, 2].map((i) => (
                <span key={i} className="w-1 h-1 rounded-full bg-[var(--accent)] animate-pulse"
                  style={{ animationDelay: `${i * 180}ms` }} />
              ))}
            </span>
          </p>
          {[88, 78, 60, 96].map((w, i) => (
            <div key={i} className="h-3 rounded bg-[var(--surface)] overflow-hidden">
              <div className="h-full bg-[var(--rule-strong)] animate-pulse" style={{ width: `${w}%` }} />
            </div>
          ))}
        </div>
      ) : status === "failed" ? (
        <>
          <p className="text-[var(--danger)] font-serif text-xl mb-3">Generation failed.</p>
          <Link
            href="/insights"
            className="inline-flex items-center justify-center rounded-lg px-4 h-9 text-sm font-medium bg-[var(--danger)] text-white transition-opacity hover:opacity-80"
          >
            View in Insights →
          </Link>
        </>
      ) : (
        <CompletedInsight insight={insight} year={year} month={month} />
      )}
    </section>
  )
}

interface InsightRecord {
  title: string | null
  description?: string | null
  impact_score?: number | null
}

function CompletedInsight({
  insight,
  year,
  month,
}: {
  insight: InsightRecord
  year: number
  month: number
}) {
  return (
    <>
      <h2 className="font-serif text-[clamp(22px,2.4vw,28px)] font-medium text-[var(--text)] mb-1">
        {insight.title}
      </h2>
      {insight.description && (
        <p className="text-sm text-[var(--text-2)] mb-4 max-w-[52ch]">
          {insight.description.slice(0, 160)}…
        </p>
      )}
      <div className="flex items-center gap-6">
        {insight.impact_score && (
          <span className="font-mono text-[24px] text-[var(--accent)]">
            {insight.impact_score}
            <span className="text-sm text-[var(--text-3)]">/10</span>
          </span>
        )}
        <Link
          href={`/insights/monthly/${year}-${String(month).padStart(2, "0")}`}
          className="inline-flex items-center justify-center rounded-lg px-2.5 h-8 text-sm font-medium bg-[var(--accent)] text-[var(--fab-fg)] transition-opacity hover:opacity-80"
        >
          Read insight →
        </Link>
      </div>
    </>
  )
}
