"use client"
import { ErrorBoundary } from "@/components/error-boundary"
import type { ReactNode } from "react"

interface Props {
  feature: string
  children: ReactNode
}

export function FeatureErrorBoundary({ feature, children }: Props) {
  return (
    <ErrorBoundary
      fallbackRender={() => (
        <div className="flex flex-col items-center justify-center min-h-[30vh] p-8 text-center">
          <p className="font-serif italic text-[18px] text-[var(--text-2)] max-w-[44ch] mb-2">
            {feature} failed to load.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="inline-flex items-center justify-center rounded-lg px-4 h-9 text-sm font-medium bg-[var(--accent)] text-[var(--fab-fg)] transition-opacity hover:opacity-80"
          >
            Reload page
          </button>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  )
}
