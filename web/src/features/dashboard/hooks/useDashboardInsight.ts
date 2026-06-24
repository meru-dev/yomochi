"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import { useInsightStream } from "@/features/insights/hooks/useInsightStream"

export function useLatestInsight(year: number, month: number) {
  // Design: SSE is the fast path (real-time status → completion push).
  // refetchInterval at 5 s is a polling backstop — it keeps the UI converging
  // even when SSE is unavailable (blocked in e2e tests, network issue, etc.)
  // so we intentionally keep it rather than removing it entirely.
  const queryKey = keys.insights.byPeriod("monthly", year, month)

  const result = useQuery({
    queryKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/insights", {
        params: { query: { limit: 1 } },
      })
      if (error) throw error
      return (data?.items ?? []).find(
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (i: any) => i.period === "monthly" && i.period_year === year && i.period_month === month
      ) ?? null
    },
    // Backstop poll: slower than the old 2 s — SSE handles the fast path.
    // Falls back to this when SSE is unavailable (tests, network degradation).
    refetchInterval: (q) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const s = (q.state.data as any)?.status
      return s === "queued" || s === "processing" ? 5000 : false
    },
  })

  // Open SSE stream when there is an in-flight insight id.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  useInsightStream((result.data as any)?.id ?? null, queryKey)

  return result
}

export function useRequestInsight() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ year, month }: { year: number; month: number }) => {
      const { data, error } = await api.POST("/api/v1/insights/requests", {
        body: { period: "monthly", period_year: year, period_month: month },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.insights.all() })
    },
  })
}
