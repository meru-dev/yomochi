"use client"
import type { UseQueryResult } from "@tanstack/react-query"
import type { ReactNode } from "react"

interface Props<T> {
  query: Pick<UseQueryResult<T>, "isLoading" | "isError" | "data">
  skeleton?: ReactNode
  error?: ReactNode
  children: (data: T) => ReactNode
}

export function QuerySkeleton<T>({ query, skeleton, error, children }: Props<T>) {
  if (query.isLoading) {
    return <>{skeleton ?? <DefaultSkeleton />}</>
  }
  if (query.isError) {
    return <>{error ?? <DefaultError />}</>
  }
  if (query.data === undefined) return null
  return <>{children(query.data)}</>
}

function DefaultSkeleton() {
  return (
    <div className="animate-pulse space-y-3 py-6">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-12 rounded-lg bg-[var(--bg-2)]" />
      ))}
    </div>
  )
}

function DefaultError() {
  return (
    <p className="py-8 text-center text-sm text-[var(--text-2)]">
      Failed to load data. Please try again.
    </p>
  )
}
