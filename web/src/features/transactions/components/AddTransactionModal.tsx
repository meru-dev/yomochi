"use client"
import type { components } from "@/lib/api/schema"
import { useState, useEffect } from "react"
import dynamic from "next/dynamic"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { transactionSchema, type TransactionFields } from "@/lib/forms/transactionSchema"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useUIStore } from "@/lib/store/ui"
import { useCreateTransaction } from "../hooks/useCreateTransaction"
import { useCategories } from "../hooks/useTransactions"
import { TransactionForm } from "./TransactionForm"

type CategoryItem = components["schemas"]["CategoryItem"]

const ParseTextStrip = dynamic(
  () => import("./ParseTextStrip").then((m) => m.ParseTextStrip),
  { ssr: false, loading: () => <div className="flex-1 h-10 rounded-[var(--radius-md)] bg-[var(--surface)] border border-[var(--rule-strong)]" /> }
)

const ReceiptUpload = dynamic(
  () => import("./ReceiptUpload").then((m) => m.ReceiptUpload),
  { ssr: false, loading: () => <div className="w-10 h-10 rounded-[var(--radius-md)] bg-[var(--surface)] border border-[var(--rule-strong)]" /> }
)

export function AddTransactionModal() {
  const { addOpen, closeAdd } = useUIStore()
  const [generalError, setGeneralError] = useState<string | null>(null)
  const [aiFilledFields, setAiFilledFields] = useState<Set<string>>(new Set())
  const [lowConfFields, setLowConfFields] = useState<Set<string>>(new Set())
  const [receiptError, setReceiptError] = useState<string | null>(null)

  const form = useForm<TransactionFields>({
    resolver: zodResolver(transactionSchema),
    defaultValues: { type: "EXPENSE", currency: "JPY", date: new Date().toISOString().slice(0, 10) },
  })

  const create = useCreateTransaction(
    (field, error) => form.setError(field as keyof TransactionFields, error),
    setGeneralError,
  )
  const { data: categoriesData } = useCategories()
  const allCategories: CategoryItem[] = categoriesData?.items ?? []

  async function onSubmit(data: TransactionFields) {
    setGeneralError(null)
    const body = {
      ...data,
      type: data.type.toLowerCase() as "expense" | "income",
    }
    if (!body.category_id) delete body.category_id
    if (!body.notes) delete body.notes
    if (!body.merchant) delete body.merchant
    create.mutate(body)
  }

  useEffect(() => {
    if (!addOpen) {
      form.reset()
      setGeneralError(null)
      setAiFilledFields(new Set())
      setLowConfFields(new Set())
      setReceiptError(null)
    }
  }, [addOpen, form])

  return (
    <Dialog open={addOpen} onOpenChange={(o) => !o && closeAdd()}>
      <DialogContent className="sm:max-w-[560px] bg-[var(--bg)] border-[var(--rule-strong)]">
        <DialogHeader>
          <DialogTitle className="font-serif text-[22px] font-medium text-[var(--text)]">
            Add transaction
          </DialogTitle>
        </DialogHeader>
        <TransactionForm
          mode="create"
          form={form}
          allCategories={allCategories}
          onSubmit={onSubmit}
          isSubmitting={create.isPending}
          generalError={generalError}
          aiFilledFields={aiFilledFields}
          lowConfFields={lowConfFields}
          topSlot={() => (
            <>
              <div className="flex gap-2 mb-4">
                <ParseTextStrip
                  setValue={form.setValue}
                  onFillChange={(filled, lowConf) => {
                    setAiFilledFields(filled)
                    setLowConfFields(lowConf)
                  }}
                />
                <ReceiptUpload
                  setValue={form.setValue}
                  allCategories={allCategories}
                  onFillChange={(filled) => setAiFilledFields(filled)}
                  onError={setReceiptError}
                />
              </div>
              {receiptError && (
                <p className="text-[var(--danger)] text-xs -mt-3 mb-3">{receiptError}</p>
              )}
            </>
          )}
        />
      </DialogContent>
    </Dialog>
  )
}
