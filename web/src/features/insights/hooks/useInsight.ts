"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import type { components } from "@/lib/api/schema"
import { useInsightStream } from "./useInsightStream"

type Insight = components["schemas"]["InsightResponse"]
type PeriodEnum = components["schemas"]["Period"]

export function useInsightByPeriod(period: string, year: number, month: number) {
  // Design: SSE is the fast path (real-time status → completion push).
  // refetchInterval at 5 s is a polling backstop — it keeps the UI converging
  // even when SSE is unavailable (blocked in e2e tests, network issue, etc.)
  // so we intentionally keep it rather than removing it entirely.
  const queryKey = keys.insights.byPeriod(period, year, month)

  const result = useQuery<Insight | null>({
    queryKey,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/insights", {
        params: {
          query: {
            limit: 1,
            period: period.toLowerCase() as PeriodEnum,
            period_year: year,
            period_month: month,
          },
        },
      })
      if (error) throw error
      return data?.items?.[0] ?? null
    },
    // Backstop poll: slower than the old 2 s — SSE handles the fast path.
    // Falls back to this when SSE is unavailable (tests, network degradation).
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === "queued" || s === "processing" ? 5000 : false
    },
  })

  // Open SSE stream when there is an in-flight insight id.
  useInsightStream(result.data?.id ?? null, queryKey)

  return result
}

export function useRequestInsightForPage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { period: string; period_year: number; period_month: number }) => {
      const period = body.period.toLowerCase() as "monthly" | "weekly"
      const { data, error } = await api.POST("/api/v1/insights/requests", {
        body: { ...body, period },
      })
      if (error) throw error
      return data
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.insights.all() }),
  })
}
