"use client"
import { TxRow } from "./TxRow"
import { useCategories } from "../hooks/useTransactions"
import type { TxData } from "@/lib/store/ui"
import type { components } from "@/lib/api/schema"

type Category = components["schemas"]["CategoryItem"]

export function TransactionList({ transactions }: { transactions: TxData[] }) {
  const { data: categoriesData } = useCategories()
  const items = (categoriesData?.items ?? []) as Category[]
  const catMap = new Map<string, Category>(items.map((c) => [c.id, c]))

  if (transactions.length === 0) return <EmptyState />

  return (
    <div className="space-y-2">
      {transactions.map((tx, i) => {
        const cat = catMap.get(tx.category_id ?? "")
        return (
          <div key={tx.id}
            className="animate-in fade-in slide-in-from-bottom-2 duration-200 fill-mode-both"
            style={{ animationDelay: `${i * 30}ms` }}>
            <TxRow tx={tx}
              categoryName={cat?.name}
              categoryColor={cat?.color ?? undefined} />
          </div>
        )
      })}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="border border-dashed border-[var(--rule-strong)] rounded-[var(--radius-lg)] p-20 text-center">
      <p className="font-serif italic text-[22px] text-[var(--text-2)] max-w-[38ch] mx-auto">
        &ldquo;There is nothing here, yet — which is itself a thing to notice.&rdquo;
      </p>
      <p className="font-mono text-[11px] text-[var(--text-3)] uppercase mt-4">
        — No transactions match your filters
      </p>
    </div>
  )
}
