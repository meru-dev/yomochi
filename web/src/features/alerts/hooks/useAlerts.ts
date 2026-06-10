"use client"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"

export interface AlertItem {
  id: string
  type: string
  title: string
  body: string
  period_year: number
  period_month: number
  is_read: boolean
  created_at: string
}

export function useAlertsUnreadCount() {
  return useQuery({
    queryKey: keys.alerts.unreadCount(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/alerts/unread-count")
      if (error) throw error
      return (data?.count ?? 0) as number
    },
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function useAlerts(enabled = true) {
  return useQuery({
    queryKey: keys.alerts.list(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/alerts", {
        params: { query: { limit: 50 } },
      })
      if (error) throw error
      return (data?.items ?? []) as AlertItem[]
    },
    enabled,
    staleTime: 10_000,
  })
}

export function useMarkAlertRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (alertId: string) => {
      const { error } = await api.PATCH("/api/v1/alerts/{alert_id}/read", {
        params: { path: { alert_id: alertId } },
      })
      if (error) throw error
    },
    onMutate: async (alertId: string) => {
      await qc.cancelQueries({ queryKey: keys.alerts.list() })
      const prev = qc.getQueryData<AlertItem[]>(keys.alerts.list())
      qc.setQueryData<AlertItem[]>(keys.alerts.list(), (old) =>
        (old ?? []).map((a) => (a.id === alertId ? { ...a, is_read: true } : a))
      )
      return { prev }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.alerts.list(), ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.alerts.unreadCount() })
    },
  })
}

export function useClearAlerts() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const { error } = await api.DELETE("/api/v1/alerts")
      if (error) throw error
    },
    onSuccess: () => {
      qc.setQueryData(keys.alerts.list(), [])
      qc.setQueryData(keys.alerts.unreadCount(), 0)
    },
  })
}
