"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  LayoutDashboard, Receipt, RefreshCw, Sparkles,
  MessageCircle, Tag, Settings, Bell, LogOut,
} from "lucide-react"
import { useLogout } from "@/features/auth/hooks/useAuth"
import { useUIStore } from "@/lib/store/ui"
import { useAlertsUnreadCount } from "@/features/alerts/hooks/useAlerts"

const NAV = [
  { label: "Dashboard",    href: "/dashboard",         Icon: LayoutDashboard },
  { label: "Transactions", href: "/transactions",       Icon: Receipt },
  { label: "Recurring",    href: "/recurring",          Icon: RefreshCw },
  { label: "Insights",     href: "/insights",           Icon: Sparkles },
  { label: "Chat",         href: "/chat",               Icon: MessageCircle },
  { label: "Categories",   href: "/categories",         Icon: Tag },
  { label: "Settings",     href: "/settings/sessions",  Icon: Settings },
]

function BellButton() {
  const { openAlerts } = useUIStore()
  const { data: count = 0 } = useAlertsUnreadCount()
  return (
    <button
      onClick={openAlerts}
      className="relative p-1.5 text-[var(--text-3)] hover:text-[var(--text)] hover:bg-[var(--surface)] transition-colors rounded-[var(--radius-sm)]"
      aria-label="Open alerts"
    >
      <Bell className="w-4 h-4" />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] rounded-full bg-[var(--accent)] text-white text-[9px] font-mono flex items-center justify-center px-[3px]">
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  )
}

export function Sidebar() {
  const path = usePathname()
  const logout = useLogout()
  return (
    <nav className="flex flex-col h-full p-4 gap-0.5">
      <div className="flex items-center justify-between mb-6 px-2">
        <span className="font-serif text-[15px] font-medium text-[var(--text)]">Yomochi</span>
        <BellButton />
      </div>

      {NAV.map(({ label, href, Icon }) => {
        const active = path === href || path.startsWith(href + "/")
        return (
          <Link key={href} href={href}
            className={`flex items-center gap-3 px-3 py-2.5 rounded-[var(--radius-md)] text-sm transition-colors
              ${active
                ? "bg-[var(--surface)] text-[var(--text)] shadow-sm"
                : "text-[var(--text-2)] hover:text-[var(--text)] hover:bg-[var(--surface)]"}`}>
            <Icon className={`w-4 h-4 shrink-0 ${active ? "text-[var(--accent)]" : ""}`} />
            <span>{label}</span>
          </Link>
        )
      })}

      <div className="mt-auto pt-4 border-t border-[var(--rule)]">
        <button
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
          className={`flex items-center gap-2.5 px-3 py-2 w-full rounded-[var(--radius-md)] text-sm transition-colors disabled:opacity-50
            ${logout.isError
              ? "text-[var(--danger)]"
              : "text-[var(--text-3)] hover:text-[var(--danger)] hover:bg-[var(--surface)]"}`}
        >
          <LogOut className="w-4 h-4 shrink-0" />
          <span className="font-mono text-xs">
            {logout.isPending ? "Signing out…" : logout.isError ? "error — retry" : "Sign out"}
          </span>
        </button>
      </div>
    </nav>
  )
}
