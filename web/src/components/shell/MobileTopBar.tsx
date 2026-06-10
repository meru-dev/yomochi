"use client"
import { Bell, Search } from "lucide-react"
import { useUIStore } from "@/lib/store/ui"
import { useAlertsUnreadCount } from "@/features/alerts/hooks/useAlerts"

export function MobileTopBar() {
  const { togglePalette, openAlerts } = useUIStore()
  const { data: count = 0 } = useAlertsUnreadCount()
  return (
    <header className="md:hidden flex items-center justify-between px-5 py-3.5 border-b border-[var(--rule)] bg-[var(--bg)]">
      <span className="font-serif text-[15px] font-medium text-[var(--text)]">Yomochi</span>
      <div className="flex items-center gap-1">
        <button
          onClick={openAlerts}
          className="relative p-2 text-[var(--text-3)] hover:text-[var(--text)] active:opacity-75 transition-colors rounded-[var(--radius-sm)]"
          aria-label="Open alerts"
        >
          <Bell className="w-5 h-5" />
          {count > 0 && (
            <span className="absolute top-1.5 right-1.5 min-w-[14px] h-[14px] rounded-full bg-[var(--accent)] text-white text-[8px] font-mono flex items-center justify-center px-[2px]">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </button>
        <button
          onClick={togglePalette}
          className="p-2 text-[var(--text-3)] hover:text-[var(--text)] active:opacity-75 transition-colors rounded-[var(--radius-sm)]"
          aria-label="Search"
        >
          <Search className="w-5 h-5" />
        </button>
      </div>
    </header>
  )
}
