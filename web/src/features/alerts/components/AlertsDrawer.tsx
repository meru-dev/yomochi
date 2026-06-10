"use client"
import { useEffect } from "react"
import { useUIStore } from "@/lib/store/ui"
import { useAlerts, useMarkAlertRead, useClearAlerts } from "../hooks/useAlerts"
import { useConfirm } from "@/hooks/useConfirm"
import { AlertItem } from "./AlertItem"

export function AlertsDrawer() {
  const { alertsOpen, closeAlerts, showToast } = useUIStore()
  const { data: alerts = [], isLoading } = useAlerts(alertsOpen)
  const markRead = useMarkAlertRead()
  const clearAll = useClearAlerts()
  const { confirm, confirmPortal } = useConfirm()

  useEffect(() => {
    if (!alertsOpen) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") closeAlerts()
    }
    window.addEventListener("keydown", onKey)
    document.body.style.overflow = "hidden"
    return () => {
      window.removeEventListener("keydown", onKey)
      document.body.style.overflow = ""
    }
  }, [alertsOpen, closeAlerts])

  if (!alertsOpen) return null

  const unread = alerts.filter((a) => !a.is_read)
  const read = alerts.filter((a) => a.is_read)

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20"
        onClick={closeAlerts}
        aria-hidden="true"
      />
      {/* drawer */}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Alerts"
        className="fixed right-0 top-0 h-full w-[340px] max-w-full z-50 bg-[var(--bg)] border-l border-[var(--rule)] shadow-xl flex flex-col"
      >
        {/* header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--rule)]">
          <h2 className="text-sm font-medium text-[var(--text)]">
            Alerts
            {unread.length > 0 && (
              <span className="ml-2 text-xs font-mono text-[var(--accent)]">
                {unread.length} new
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3">
            {alerts.length > 0 && (
              <button
                onClick={async () => {
                  if (!await confirm("Delete all alerts? This cannot be undone.")) return
                  clearAll.mutate(undefined, { onError: () => showToast({ message: "Failed to clear alerts", ttl: 3000 }) })
                }}
                disabled={clearAll.isPending}
                className="text-[10px] font-mono text-[var(--text-3)] hover:text-[var(--danger)] transition-colors disabled:opacity-40"
              >
                {clearAll.isPending ? "clearing…" : "clear all"}
              </button>
            )}
            <button
              onClick={closeAlerts}
              className="text-[var(--text-3)] hover:text-[var(--text)] transition-colors text-lg leading-none"
              aria-label="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* content */}
        <div className="flex-1 overflow-y-auto px-5 py-2">
          {isLoading && (
            <p className="text-sm text-[var(--text-3)] text-center pt-8">Loading…</p>
          )}
          {!isLoading && alerts.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-2 text-center">
              <span className="text-2xl opacity-30">🔔</span>
              <p className="text-sm text-[var(--text-3)]">No alerts yet.</p>
              <p className="text-xs text-[var(--text-3)]">
                Alerts appear when your spending shifts by 30%+ vs your recent average.
              </p>
            </div>
          )}
          {unread.length > 0 && (
            <div>
              {unread.map((a) => (
                <AlertItem key={a.id} alert={a} onMarkRead={(id) => markRead.mutate(id, { onError: () => showToast({ message: "Failed to mark alert as read", ttl: 3000 }) })} />
              ))}
            </div>
          )}
          {read.length > 0 && (
            <div className="mt-3">
              <p className="text-[10px] font-mono text-[var(--text-3)] uppercase tracking-wider mb-1">
                Read
              </p>
              {read.map((a) => (
                <AlertItem key={a.id} alert={a} onMarkRead={(id) => markRead.mutate(id, { onError: () => showToast({ message: "Failed to mark alert as read", ttl: 3000 }) })} />
              ))}
            </div>
          )}
        </div>
        {confirmPortal}
      </div>
    </>
  )
}
