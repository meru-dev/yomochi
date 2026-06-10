"use client"
import { Suspense } from "react"
import { Sidebar } from "./Sidebar"
import { MobileTopBar } from "./MobileTopBar"
import { MobileBottomNav } from "./MobileBottomNav"
import { ToastQueue } from "./ToastQueue"
import { AddTransactionModal } from "@/features/transactions/components/AddTransactionModal"
import { EditTransactionModal } from "@/features/transactions/components/EditTransactionModal"
import { CommandPalette } from "@/features/search/components/CommandPalette"
import { AlertsDrawer } from "@/features/alerts/components/AlertsDrawer"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import { ErrorBoundary } from "@/components/error-boundary"

function MainSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-8 w-1/3 bg-[var(--surface)] rounded" />
      <div className="h-4 w-1/2 bg-[var(--surface)] rounded" />
      <div className="h-32 bg-[var(--surface)] rounded mt-6" />
    </div>
  )
}

export function AppShell({ children }: { children: React.ReactNode }) {
  useKeyboardShortcuts()
  return (
    <div className="grid min-h-screen md:[grid-template-columns:220px_1fr]">
      <aside className="hidden md:block border-r border-[var(--rule)] sticky top-0 h-screen">
        <Sidebar />
      </aside>
      <div className="flex flex-col min-h-screen overflow-x-hidden">
        <MobileTopBar />
        <main className="flex-1 px-[clamp(20px,5vw,72px)] pt-10 pb-20">
          <ErrorBoundary>
            <Suspense fallback={<MainSkeleton />}>{children}</Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <MobileBottomNav />
      <AddTransactionModal />
      <EditTransactionModal />
      <CommandPalette />
      <ToastQueue />
      <AlertsDrawer />
    </div>
  )
}
