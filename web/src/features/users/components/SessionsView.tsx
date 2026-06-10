"use client"
import { useSessions, useRevokeSession } from "../hooks/useSessions"
import { PageHead } from "@/components/shell/PageHead"

function formatUA(ua: string): string {
  if (ua.includes("Chrome")) return "Chrome"
  if (ua.includes("Firefox")) return "Firefox"
  if (ua.includes("Safari")) return "Safari"
  if (ua.includes("Edge")) return "Edge"
  return ua.slice(0, 40)
}

function formatExpiry(iso: string): string {
  return new Date(iso).toLocaleString("default", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function SessionsView() {
  const { data: sessions, isLoading, isError } = useSessions()
  const revoke = useRevokeSession()

  return (
    <div>
      <PageHead crumb="SETTINGS" title="Active sessions" />

      <p className="font-mono text-xs text-[var(--text-3)] mb-6">
        Each entry is an active login. Revoke any session you don&apos;t recognise.
      </p>

      {isLoading && (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-14 bg-[var(--surface)] rounded animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="font-mono text-sm text-[var(--danger)]">Failed to load sessions.</p>
      )}

      {!isLoading && !isError && (!sessions || sessions.length === 0) && (
        <p className="font-mono text-sm text-[var(--text-3)]">No active sessions found.</p>
      )}

      {!isLoading && sessions && sessions.length > 0 && (
        <div className="border border-[var(--rule)] rounded-[3px] divide-y divide-[var(--rule)]">
          {sessions.map((s) => (
            <div key={s.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="font-mono text-sm text-[var(--text)] truncate">{formatUA(s.user_agent)}</p>
                <p className="font-mono text-xs text-[var(--text-3)]">
                  {s.ip} · expires {formatExpiry(s.expires_at)}
                </p>
              </div>
              <button
                onClick={() => revoke.mutate(s.id)}
                disabled={revoke.isPending}
                className="shrink-0 font-mono text-xs text-[var(--danger)] hover:opacity-80 disabled:opacity-40 transition-opacity"
              >
                Revoke
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
