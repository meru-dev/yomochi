"use client"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"
import { keys } from "@/lib/query/keys"
import { useUIStore } from "@/lib/store/ui"
import { parseApiError } from "@/lib/api/parseApiError"

type UpdateTransactionRequest = components["schemas"]["UpdateTransactionRequest"]

type CachedPage = { items: ({ id: string } & Record<string, unknown>)[] } & Record<string, unknown>

export type UpdateTransactionBody = UpdateTransactionRequest & { id: string }

interface MutationContext {
  prev: [readonly unknown[], unknown][]
}

export function useUpdateTransaction(
  setError: (field: string, error: { message: string }) => void,
  setGeneralError: (msg: string | null) => void,
) {
  const qc = useQueryClient()
  const { closeEdit, showToast } = useUIStore()

  return useMutation<void, unknown, UpdateTransactionBody, MutationContext>({
    mutationFn: async ({ id, ...body }) => {
      const { error } = await api.PATCH("/api/v1/transactions/{transaction_id}", {
        params: { path: { transaction_id: id } },
        body,
      })
      if (error) throw error
    },
    onMutate: async ({ id, ...body }) => {
      setGeneralError(null)
      await qc.cancelQueries({ queryKey: keys.transactions.all() })
      const prev = qc.getQueriesData({ queryKey: keys.transactions.all() })
      qc.setQueriesData({ queryKey: keys.transactions.all() }, (old: CachedPage | undefined) =>
        old && "items" in old
          ? { ...old, items: old.items.map((t) => t.id === id ? { ...t, ...body } : t) }
          : old
      )
      return { prev }
    },
    onError: (err, _vars, ctx) => {
      ctx?.prev.forEach(([key, data]) => qc.setQueryData(key, data))
      const parsed = parseApiError(err)
      parsed.fieldErrors.forEach(({ field, message }) =>
        setError(field, { message })
      )
      setGeneralError(parsed.generalError)
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: keys.transactions.all() })
      closeEdit()
      showToast({
        message: "✓ Updated.",
        meta: [vars.currency, vars.amount, vars.merchant ? `· ${vars.merchant}` : ""]
          .filter(Boolean)
          .join(" "),
        ttl: 3000,
      })
    },
  })
}
