"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import type { components } from "@/lib/api/schema"

type Insight = components["schemas"]["InsightResponse"]
type PeriodEnum = components["schemas"]["Period"]

export function useInsightByPeriod(period: string, year: number, month: number) {
  return useQuery<Insight | null>({
    queryKey: keys.insights.byPeriod(period, year, month),
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
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === "queued" || s === "processing" ? 2000 : false
    },
  })
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
