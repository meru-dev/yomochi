"use client"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import { keys } from "@/lib/query/keys"
import { useUIStore } from "@/lib/store/ui"
import type { TxData } from "@/lib/store/ui"

type CachedPage = { items: { id: string }[] } & Record<string, unknown>

interface MutationContext {
  prev: [readonly unknown[], unknown][]
}

export function useDeleteTransaction() {
  const qc = useQueryClient()
  const { showToast } = useUIStore()

  return useMutation<void, unknown, TxData, MutationContext>({
    mutationFn: async (tx) => {
      const { error } = await api.DELETE("/api/v1/transactions/{transaction_id}", {
        params: { path: { transaction_id: tx.id } },
      })
      if (error) throw error
    },
    onMutate: async (tx) => {
      await qc.cancelQueries({ queryKey: keys.transactions.all() })
      const prev = qc.getQueriesData({ queryKey: keys.transactions.all() })
      qc.setQueriesData({ queryKey: keys.transactions.all() }, (old: CachedPage | undefined) =>
        old && "items" in old
          ? { ...old, items: old.items.filter((t) => t.id !== tx.id) }
          : old
      )
      return { prev }
    },
    onError: (_err, _tx, ctx) => {
      ctx?.prev.forEach(([key, data]) => qc.setQueryData(key, data))
      showToast({ message: "Failed to delete transaction.", ttl: 4000 })
    },
    onSuccess: (_data, tx) => {
      qc.invalidateQueries({ queryKey: keys.transactions.all() })
      showToast({
        message: "✓ Deleted.",
        meta: `${tx.currency} ${tx.amount}${tx.merchant ? ` · ${tx.merchant}` : ""}`,
        undo: async () => {
          await api.POST("/api/v1/transactions", {
            body: {
              amount: tx.amount,
              currency: tx.currency,
              date: tx.date,
              type: tx.type.toLowerCase() as "income" | "expense",
              ...(tx.merchant ? { merchant: tx.merchant } : {}),
              ...(tx.notes ? { notes: tx.notes } : {}),
              ...(tx.category_id ? { category_id: tx.category_id } : {}),
            },
          })
          qc.invalidateQueries({ queryKey: keys.transactions.all() })
        },
        ttl: 4200,
      })
    },
  })
}
