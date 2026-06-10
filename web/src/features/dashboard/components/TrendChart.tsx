"use client"
import { useState, useMemo } from "react"
import { useTrend } from "../hooks/useReports"

type Granularity = "month" | "week"

const W = 360 // svg viewBox width
const H = 80  // svg viewBox height
const PAD = { left: 6, right: 6, top: 8, bottom: 18 }

function lastNPeriods(n: number, gran: Granularity): string[] {
  const result: string[] = []
  const now = new Date()
  if (gran === "month") {
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
      result.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`)
    }
  } else {
    // ISO week — derive from Monday of each week back
    const monday = new Date(now)
    const day = monday.getDay() || 7
    monday.setDate(monday.getDate() - day + 1)
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date(monday)
      d.setDate(monday.getDate() - i * 7)
      result.push(isoYearWeek(d))
    }
  }
  return result
}

function isoYearWeek(d: Date): string {
  // ISO 8601 year+week — matches Postgres `to_char(date, 'IYYY-"W"IW')`
  const target = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  const dayNum = target.getUTCDay() || 7
  target.setUTCDate(target.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1))
  const weekNum = Math.ceil((((target.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  return `${target.getUTCFullYear()}-W${String(weekNum).padStart(2, "0")}`
}

function labelFor(key: string, gran: Granularity): string {
  if (gran === "month") {
    return new Date(key + "-01").toLocaleString("default", { month: "short" })
  }
  return key.split("-W")[1] ?? key
}

interface TrendChartProps {
  currency?: string
}

export function TrendChart({ currency = "JPY" }: TrendChartProps) {
  const [gran, setGran] = useState<Granularity>("month")
  const count = gran === "month" ? 6 : 12

  const { data: expenseData, isLoading: expLoading } = useTrend(currency, count, "expense", gran)
  const { data: incomeData, isLoading: incLoading } = useTrend(currency, count, "income", gran)
  const isLoading = expLoading || incLoading

  const series = useMemo(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const expensePoints: any[] = (expenseData as any)?.points ?? []
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const incomePoints: any[] = (incomeData as any)?.points ?? []
    const expMap = new Map<string, number>(expensePoints.map((p) => [p.month, parseFloat(p.total)]))
    const incMap = new Map<string, number>(incomePoints.map((p) => [p.month, parseFloat(p.total)]))
    const keys = lastNPeriods(count, gran)
    return keys.map((k) => ({
      key: k,
      label: labelFor(k, gran),
      expense: expMap.get(k) ?? 0,
      income: incMap.get(k) ?? 0,
    }))
  }, [expenseData, incomeData, gran, count])

  const maxVal = Math.max(...series.map((s) => Math.max(s.expense, s.income)), 1)

  function path(values: number[]): string {
    if (values.length === 0) return ""
    const innerW = W - PAD.left - PAD.right
    const innerH = H - PAD.top - PAD.bottom
    const stepX = values.length > 1 ? innerW / (values.length - 1) : 0
    return values
      .map((v, i) => {
        const x = PAD.left + i * stepX
        const y = PAD.top + innerH - (v / maxVal) * innerH
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(" ")
  }

  return (
    <div className="p-5 rounded-[var(--radius-lg)] bg-[var(--surface)] shadow-sm flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)]">
          {currency} · {gran === "month" ? `${count} months` : `${count} weeks`}
        </p>
        <div className="flex border border-[var(--rule-strong)] rounded-[var(--radius-sm)] overflow-hidden">
          {(["month", "week"] as const).map((g) => (
            <button
              key={g}
              type="button"
              onClick={() => setGran(g)}
              className={`px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest transition-colors
                ${gran === g ? "bg-[var(--accent)] text-[var(--fab-fg)]" : "text-[var(--text-3)] hover:text-[var(--text)]"}`}
            >
              {g}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="h-[80px] rounded animate-pulse bg-[var(--rule)]" />
      ) : (
        <svg viewBox={`0 0 ${W} ${H - PAD.bottom}`} className="w-full h-[62px]" preserveAspectRatio="none">
          {/* Income line (behind, green) */}
          <path
            d={path(series.map((s) => s.income))}
            fill="none"
            stroke="var(--income)"
            strokeWidth="1.5"
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity="0.6"
          />
          {/* Expense line (front, accent) */}
          <path
            d={path(series.map((s) => s.expense))}
            fill="none"
            stroke="var(--accent)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </svg>
      )}
      {!isLoading && (
        <div className="flex justify-between mt-1">
          {series.map((s) => (
            <span key={s.key} className="font-mono text-[9px] text-[var(--text-3)]">{s.label}</span>
          ))}
        </div>
      )}

      <div className="flex gap-4 mt-2 font-mono text-[10px] text-[var(--text-3)]">
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-[2px] bg-[var(--accent)]" /> Expense
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-[2px] bg-[var(--income)] opacity-60" /> Income
        </span>
      </div>
    </div>
  )
}
