"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import type { components } from "@/lib/api/schema"

export type InsightItem = components["schemas"]["InsightResponse"]

export function useInsightsList(limit = 50) {
  return useQuery({
    queryKey: keys.insights.list(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/insights", { params: { query: { limit } } })
      if (error) throw error
      return data?.items ?? []
    },
    refetchInterval: (q) => {
      const items = q.state.data as InsightItem[] | undefined
      const hasInFlight = items?.some(
        (i) => i.status === "queued" || i.status === "processing"
      )
      return hasInFlight ? 3000 : false
    },
  })
}
