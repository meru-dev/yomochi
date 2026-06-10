"use client"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"

export interface SessionItem {
  id: string
  user_agent: string
  ip: string
  expires_at: string
}

export function useSessions() {
  return useQuery({
    queryKey: keys.sessions.list(),
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/users/me/sessions")
      if (error) throw error
      return (data ?? []) as SessionItem[]
    },
    staleTime: 30_000,
  })
}

export function useRevokeSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionId: string) => {
      const { error } = await api.DELETE("/api/v1/users/me/sessions/{session_id}", {
        params: { path: { session_id: sessionId } },
      })
      if (error) throw error
    },
    onMutate: async (sessionId: string) => {
      await qc.cancelQueries({ queryKey: keys.sessions.list() })
      const prev = qc.getQueryData<SessionItem[]>(keys.sessions.list())
      qc.setQueryData<SessionItem[]>(keys.sessions.list(), (old) =>
        (old ?? []).filter((s) => s.id !== sessionId)
      )
      return { prev }
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.sessions.list(), ctx.prev)
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: keys.sessions.list() })
    },
  })
}
