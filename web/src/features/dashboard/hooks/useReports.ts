"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"


export function useSummary(year: number, month: number) {
  return useQuery({
    queryKey: keys.reports.summary(year, month),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/reports/summary", {
        params: { query: { year, month } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useTrend(
  currency: string,
  months = 6,
  txType?: string,
  granularity: "month" | "week" = "month",
) {
  return useQuery({
    queryKey: keys.reports.trend(currency, months, txType, granularity),
    queryFn: async () => {
      const query = { currency, months, granularity, ...(txType ? { type: txType } : {}) }
      const { data, error } = await api.GET("/api/v1/reports/trend", {
        params: { query },
      })
      if (error) throw error
      return data
    },
  })
}
