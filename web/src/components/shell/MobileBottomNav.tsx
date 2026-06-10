"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { LayoutDashboard, Receipt, Plus, Sparkles, MessageCircle } from "lucide-react"
import { useUIStore } from "@/lib/store/ui"

export function MobileBottomNav() {
  const path = usePathname()
  const { openAdd } = useUIStore()
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 flex items-end border-t border-[var(--rule)] bg-[var(--bg)]/95 backdrop-blur-sm z-40">
      <Link href="/dashboard"
        className={`flex-1 flex flex-col items-center gap-0.5 py-3 transition-colors ${path === "/dashboard" ? "text-[var(--accent)]" : "text-[var(--text-3)]"}`}>
        <LayoutDashboard className="w-5 h-5" />
        <span className="text-[10px] font-mono">Home</span>
      </Link>
      <Link href="/transactions"
        className={`flex-1 flex flex-col items-center gap-0.5 py-3 transition-colors ${path === "/transactions" ? "text-[var(--accent)]" : "text-[var(--text-3)]"}`}>
        <Receipt className="w-5 h-5" />
        <span className="text-[10px] font-mono">Transactions</span>
      </Link>
      <button onClick={openAdd} className="flex-1 flex flex-col items-center py-2" aria-label="Add transaction">
        <span className="w-12 h-12 rounded-full bg-[var(--accent)] flex items-center justify-center shadow-lg -mt-5">
          <Plus className="w-5 h-5 text-white" />
        </span>
      </button>
      <Link href="/insights"
        className={`flex-1 flex flex-col items-center gap-0.5 py-3 transition-colors ${path.startsWith("/insights") ? "text-[var(--accent)]" : "text-[var(--text-3)]"}`}>
        <Sparkles className="w-5 h-5" />
        <span className="text-[10px] font-mono">Insights</span>
      </Link>
      <Link href="/chat"
        className={`flex-1 flex flex-col items-center gap-0.5 py-3 transition-colors ${path === "/chat" ? "text-[var(--accent)]" : "text-[var(--text-3)]"}`}>
        <MessageCircle className="w-5 h-5" />
        <span className="text-[10px] font-mono">Chat</span>
      </Link>
    </nav>
  )
}
