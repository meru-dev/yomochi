"use client"
import { useEffect } from "react"
import { useUIStore, ToastSpec } from "@/lib/store/ui"

export function ToastQueue() {
  const { toasts, dismissToast } = useUIStore()
  return (
    <div className="fixed bottom-[76px] md:bottom-6 left-1/2 -translate-x-1/2 flex flex-col gap-2 z-50">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={() => dismissToast(toast.id)} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onDismiss }: { toast: ToastSpec; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, toast.ttl)
    return () => clearTimeout(t)
  }, [toast.ttl, onDismiss])

  return (
    <div className="flex items-center gap-4 px-5 py-3 bg-[var(--surface)] border border-[var(--rule-strong)] rounded-[3px] shadow-[0_12px_32px_rgba(0,0,0,0.32)] text-sm">
      <span className="text-[var(--text)]">{toast.message}</span>
      {toast.meta && <span className="text-[var(--text-3)] font-mono text-xs">{toast.meta}</span>}
      {toast.undo && (
        <button onClick={() => { toast.undo?.(); onDismiss() }}
          className="font-mono text-xs text-[var(--accent)] hover:underline">
          Undo
        </button>
      )}
      <button
        onClick={onDismiss}
        className="ml-auto text-[var(--text-3)] hover:text-[var(--text)] text-sm leading-none flex-shrink-0"
        aria-label="Dismiss">
        ✕
      </button>
    </div>
  )
}
