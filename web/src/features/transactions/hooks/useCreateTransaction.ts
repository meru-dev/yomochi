"use client"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api/client"
import type { components } from "@/lib/api/schema"
import { keys } from "@/lib/query/keys"
import { useUIStore } from "@/lib/store/ui"
import { parseApiError } from "@/lib/api/parseApiError"

export type CreateTransactionBody = components["schemas"]["CreateTransactionRequest"]
type CreateTransactionResponse = components["schemas"]["CreateTransactionResponse"]

interface CachedPage {
  items: { id: string }[]
  [k: string]: unknown
}

interface MutationContext {
  prev: [readonly unknown[], unknown][]
}

export function useCreateTransaction(
  setError: (field: string, error: { message: string }) => void,
  setGeneralError: (msg: string | null) => void,
) {
  const qc = useQueryClient()
  const { closeAdd, showToast } = useUIStore()

  return useMutation<CreateTransactionResponse, unknown, CreateTransactionBody, MutationContext>({
    mutationFn: async (body) => {
      const { data, error } = await api.POST("/api/v1/transactions", { body })
      if (error) throw error
      if (!data) throw new Error("create_transaction returned no data")
      return data
    },
    onMutate: async (body) => {
      setGeneralError(null)
      await qc.cancelQueries({ queryKey: keys.transactions.all() })
      const prev = qc.getQueriesData({ queryKey: keys.transactions.all() })
      qc.setQueriesData({ queryKey: keys.transactions.all() }, (old: CachedPage | undefined) =>
        old && "items" in old
          ? { ...old, items: [{ ...body, id: `opt-${Date.now()}` }, ...old.items] }
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
    onSuccess: (tx, vars) => {
      qc.invalidateQueries({ queryKey: keys.transactions.all() })
      closeAdd()
      showToast({
        message: "✓ Saved.",
        meta: `${vars.currency} ${vars.amount}${vars.merchant ? ` · ${vars.merchant}` : ""}`,
        undo: async () => {
          await api.DELETE("/api/v1/transactions/{transaction_id}", {
            params: { path: { transaction_id: tx.id } },
          })
          qc.invalidateQueries({ queryKey: keys.transactions.all() })
        },
        ttl: 4200,
      })
    },
  })
}
