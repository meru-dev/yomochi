"use client"
import { useEffect, useState, Suspense } from "react"
import { useSearchParams } from "next/navigation"
import { useUIStore } from "@/lib/store/ui"
import { useTransactions } from "../hooks/useTransactions"
import { TransactionList } from "./TransactionList"
import { FilterBar } from "./FilterBar"
import { Pagination } from "./Pagination"
import { PageHead } from "@/components/shell/PageHead"
import { Button } from "@/components/ui/button"
import { useSearch } from "@/features/search/hooks/useSearch"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"
import type { TxData } from "@/lib/store/ui"

function TransactionsViewInner() {
  const sp = useSearchParams()
  const { setFocusedTxIds, openAdd } = useUIStore()

  useEffect(() => {
    const focus = sp.get("focus")
    if (focus) setFocusedTxIds(focus.split(","))
  }, [sp, setFocusedTxIds])

  const filters = {
    type: sp.get("type") ?? undefined,
    currency: sp.get("currency") ?? undefined,
    category_id: sp.get("category_id") ?? undefined,
    cursor: sp.get("cursor") ?? undefined,
  }
  const { data, isLoading, isError } = useTransactions(filters)

  const [searchQuery, setSearchQuery] = useState("")
  const debouncedQuery = useDebouncedValue(searchQuery, 400)
  const search = useSearch(debouncedQuery)
  const isSearchActive = searchQuery.length >= 3 && debouncedQuery.length >= 3

  function clearSearch() {
    setSearchQuery("")
  }

  const items: TxData[] = isSearchActive
    ? (search.data?.items ?? []).map((item) => ({
        ...item,
        category_id: null,
        recurring_rule_id: null,
      }))
    : (data?.items ?? [])

  return (
    <div>
      <PageHead
        crumb="TRANSACTIONS"
        title="Ledger"
        actions={
          <Button onClick={openAdd}
            className="bg-[var(--accent)] text-[var(--fab-fg)] text-sm">
            + Add transaction
          </Button>
        }
      />

      {/* Search bar — always visible above FilterBar */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] border mb-3 transition-colors
        ${isSearchActive
          ? "border-[var(--accent)] bg-[var(--accent)]/10"
          : "border-[var(--rule-strong)] bg-[var(--surface)]"}`}>
        <span className="text-[var(--accent)] text-sm select-none">✦</span>
        <input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Search transactions…"
          className="flex-1 bg-transparent border-none outline-none text-sm text-[var(--text)] placeholder:text-[var(--text-3)] font-sans"
        />
        {search.isFetching && (
          <span className="font-mono text-[10px] text-[var(--text-3)] animate-pulse">searching…</span>
        )}
        {!search.isFetching && !isSearchActive && (
          <span className="font-mono text-[10px] text-[var(--text-3)] uppercase tracking-widest bg-[var(--surface)] border border-[var(--rule-strong)] px-1.5 py-0.5 rounded">AI</span>
        )}
        {isSearchActive && (
          <button onClick={clearSearch}
            className="text-[var(--text-3)] hover:text-[var(--text)] text-sm leading-none font-mono">×</button>
        )}
      </div>

      {/* Status line when search active */}
      {isSearchActive && (
        <p className="font-mono text-[11px] text-[var(--text-3)] mb-3">
          {search.isFetching ? "Searching…" : `${items.length} result${items.length !== 1 ? "s" : ""}`}
          {" · "}
          <button onClick={clearSearch} className="text-[var(--accent)] hover:underline">clear</button>
        </p>
      )}

      {/* FilterBar — hidden during search */}
      {!isSearchActive && <FilterBar />}

      {isError && !isSearchActive && (
        <p className="font-mono text-sm text-[var(--danger)] py-8 text-center">Failed to load transactions.</p>
      )}

      {isLoading && !isSearchActive ? (
        <div className="space-y-2">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-14 bg-[var(--surface)] rounded animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 && isSearchActive && !search.isFetching ? (
        <p className="font-mono text-sm text-[var(--text-3)] py-8 text-center">No results found.</p>
      ) : isSearchActive && search.isFetching ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-14 bg-[var(--surface)] rounded animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 && !isSearchActive ? (
        <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] p-10 text-center mt-4">
          <p className="font-serif text-xl text-[var(--text)] mb-2">No transactions yet.</p>
          <p className="text-sm text-[var(--text-2)] max-w-[44ch] mx-auto mb-5">
            Add your first transaction to start building your financial memory. You can also paste free text
            like <code className="font-mono text-[var(--accent)]">&quot;coffee 380 yesterday&quot;</code> — Yomochi will parse it.
          </p>
          <Button onClick={openAdd} className="bg-[var(--accent)] text-[var(--fab-fg)]">
            + Add first transaction
          </Button>
        </div>
      ) : (
        <TransactionList transactions={items} />
      )}

      {/* Pagination — hidden during search */}
      {!isSearchActive && <Pagination nextCursor={data?.next_cursor ?? null} />}
    </div>
  )
}

export function TransactionsView() {
  return (
    <Suspense fallback={
      <div className="space-y-2">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-14 bg-[var(--surface)] rounded animate-pulse" />
        ))}
      </div>
    }>
      <TransactionsViewInner />
    </Suspense>
  )
}
