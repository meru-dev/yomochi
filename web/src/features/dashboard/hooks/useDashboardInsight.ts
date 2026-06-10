"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"


export function useLatestInsight(year: number, month: number) {
  return useQuery({
    queryKey: keys.insights.byPeriod("monthly", year, month),
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
    refetchInterval: (q) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const s = (q.state.data as any)?.status
      return s === "queued" || s === "processing" ? 2000 : false
    },
  })
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
