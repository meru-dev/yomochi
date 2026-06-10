"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"

export function useSearch(query: string) {
  return useQuery({
    queryKey: keys.search.result(query),
    queryFn: async ({ signal }) => {
      const { data, error } = await api.POST("/api/v1/search", {
        body: { query, limit: 20 },
        signal,
      })
      if (error) throw error
      return data
    },
    enabled: query.length >= 3,
    staleTime: 30_000,
  })
}
