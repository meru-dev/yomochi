"use client"
import type { components } from "@/lib/api/schema"
import { useState, useEffect } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { transactionSchema, type TransactionFields } from "@/lib/forms/transactionSchema"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useUIStore } from "@/lib/store/ui"
import { useUpdateTransaction } from "../hooks/useUpdateTransaction"
import { useCategories } from "../hooks/useTransactions"
import { TransactionForm } from "./TransactionForm"

type CategoryItem = components["schemas"]["CategoryItem"]

export function EditTransactionModal() {
  const { editingTx, closeEdit } = useUIStore()
  const [generalError, setGeneralError] = useState<string | null>(null)

  const form = useForm<TransactionFields>({ resolver: zodResolver(transactionSchema) })

  const update = useUpdateTransaction(
    (field, error) => form.setError(field as keyof TransactionFields, error),
    setGeneralError,
  )
  const { data: categoriesData } = useCategories()
  const allCategories: CategoryItem[] = categoriesData?.items ?? []

  useEffect(() => {
    if (!editingTx) return
    form.reset({
      type: editingTx.type.toUpperCase() as "EXPENSE" | "INCOME",
      amount: parseFloat(editingTx.amount).toString(),
      currency: editingTx.currency as "JPY" | "USD" | "EUR" | "GBP",
      date: editingTx.date,
      merchant: editingTx.merchant ?? "",
      notes: editingTx.notes ?? "",
      category_id: editingTx.category_id ?? "",
    })
    setGeneralError(null)
  }, [editingTx, form])

  async function onSubmit(data: TransactionFields) {
    if (!editingTx) return
    setGeneralError(null)
    update.mutate({
      id: editingTx.id,
      ...data,
      type: data.type.toLowerCase() as "expense" | "income",
      category_id: data.category_id || null,
      notes: data.notes || null,
      merchant: data.merchant || null,
    })
  }

  return (
    <Dialog open={!!editingTx} onOpenChange={(o) => !o && !update.isPending && closeEdit()}>
      <DialogContent className="sm:max-w-[560px] bg-[var(--bg)] border-[var(--rule-strong)]">
        <DialogHeader>
          <DialogTitle className="font-serif text-[22px] font-medium text-[var(--text)]">
            Edit transaction
          </DialogTitle>
        </DialogHeader>
        <TransactionForm
          mode="edit"
          form={form}
          allCategories={allCategories}
          onSubmit={onSubmit}
          isSubmitting={update.isPending}
          generalError={generalError}
        />
      </DialogContent>
    </Dialog>
  )
}
