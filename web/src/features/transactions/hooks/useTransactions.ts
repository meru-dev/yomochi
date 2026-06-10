"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"

export interface TxFilters {
  type?: string
  currency?: string
  category_id?: string
  cursor?: string
  limit?: number
}

export function useTransactions(filters: TxFilters = {}) {
  return useQuery({
    queryKey: keys.transactions.list(filters as Record<string, unknown>),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/transactions", {
        params: { query: {
          limit: filters.limit ?? 20,
          cursor: filters.cursor,
          type: filters.type,
          currency: filters.currency,
          category_id: filters.category_id,
        } },
      })
      if (error) throw error
      return data
    },
  })
}

export function useCategories() {
  return useQuery({
    queryKey: keys.categories.list(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/categories")
      if (error) throw error
      return data
    },
  })
}
