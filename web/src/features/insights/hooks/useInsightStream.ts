"use client"
import { useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import type { components } from "@/lib/api/schema"

type Insight = components["schemas"]["InsightResponse"]
type QueryKey = readonly unknown[]

const TERMINAL_STATUSES = new Set(["completed", "failed"])
const ACTIVE_STATUSES = new Set(["pending", "queued", "processing"])

/**
 * Opens an SSE connection to /api/v1/insights/{id}/stream and writes frames
 * directly into the TanStack Query cache under `queryKey`.
 *
 * SSE is the fast path. The caller keeps a slow polling backstop (refetchInterval)
 * so that if SSE is unavailable (blocked in tests, network issue, etc.) the UI
 * still converges via the regular GET.
 *
 * Conditions for opening:
 *  - id must be non-null
 *  - the current cached insight must have an active (non-terminal) status
 */
export function useInsightStream(
  id: string | null,
  queryKey: QueryKey,
) {
  const queryClient = useQueryClient()

  useEffect(() => {
    if (!id) return

    // Only open the stream when the cached insight is still in-flight.
    const cached = queryClient.getQueryData<Insight | null>(queryKey)
    const status = cached?.status
    if (status && !ACTIVE_STATUSES.has(status)) return

    const url = `/api/v1/insights/${id}/stream`
    const es = new EventSource(url)

    es.onmessage = (event: MessageEvent) => {
      let frame: Record<string, unknown>
      try {
        frame = JSON.parse(event.data as string) as Record<string, unknown>
      } catch {
        return
      }

      const type = frame.type as string

      if (type === "status") {
        // Intermediate status transition (queued → processing etc.)
        // Update only the status field so the UI reflects progress.
        const newStatus = frame.status as string
        queryClient.setQueryData<Insight | null>(queryKey, (prev) =>
          prev ? { ...prev, status: newStatus } : prev,
        )
        return
      }

      if (type === "completed") {
        // Terminal — full insight object is in the frame; strip the `type` discriminant.
        const { type: _type, ...insight } = frame
        void _type
        queryClient.setQueryData<Insight | null>(queryKey, insight as Insight)
        es.close()
        return
      }

      if (type === "error") {
        // Terminal — generation failed.
        const newStatus = (frame.status as string | undefined) ?? "failed"
        const errorMessage = (frame.error_message as string | null | undefined) ?? null
        queryClient.setQueryData<Insight | null>(queryKey, (prev) =>
          prev ? { ...prev, status: newStatus, error_message: errorMessage } : prev,
        )
        es.close()
        return
      }

      if (type === "timeout") {
        // Server hit its cap without completing. Close the SSE and let the
        // polling backstop (configured in the calling hook) take over.
        es.close()
        queryClient.invalidateQueries({ queryKey })
        return
      }
    }

    es.onerror = () => {
      // Network drop, 404, or proxy returned non-SSE content.
      // EventSource would auto-reconnect — close to prevent a reconnect loop.
      // Invalidate so the polling backstop picks up the current server state.
      es.close()
      queryClient.invalidateQueries({ queryKey })
    }

    return () => {
      // Cleanup on unmount or when id/queryKey changes (React 18 StrictMode safe).
      es.close()
    }
    // We intentionally capture `queryKey` by reference as a serialised dep below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, queryClient, JSON.stringify(queryKey)])
}

export { TERMINAL_STATUSES, ACTIVE_STATUSES }
