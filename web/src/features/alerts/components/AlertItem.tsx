import type { AlertItem as AlertItemType } from "../hooks/useAlerts"

const MONTH_NAMES = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]

export function AlertItem({
  alert,
  onMarkRead,
}: {
  alert: AlertItemType
  onMarkRead: (id: string) => void
}) {
  const periodLabel = `${MONTH_NAMES[alert.period_month] ?? ""} ${alert.period_year}`

  return (
    <div
      className={`flex flex-col gap-1 py-3 px-1 border-b border-[var(--rule)] last:border-0 ${
        alert.is_read ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5 flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {!alert.is_read && (
              <span className="w-2 h-2 rounded-full bg-[var(--accent)] shrink-0" />
            )}
            <span className="text-sm font-medium text-[var(--text)] truncate">
              {alert.title}
            </span>
          </div>
          <p className={`text-xs text-[var(--text-2)] leading-relaxed ${!alert.is_read ? "pl-4" : ""}`}>
            {alert.body}
          </p>
          <span className={`text-[10px] font-mono text-[var(--text-3)] ${!alert.is_read ? "pl-4" : ""}`}>
            {periodLabel}
          </span>
        </div>
        {!alert.is_read && (
          <button
            onClick={() => onMarkRead(alert.id)}
            className="text-[10px] font-mono text-[var(--text-3)] hover:text-[var(--accent)] transition-colors shrink-0 pt-0.5"
            aria-label="Mark as read"
          >
            ✓
          </button>
        )}
      </div>
    </div>
  )
}
