"use client"
import { useRef } from "react"
import { useParseReceipt } from "@/features/ingestion/hooks/useParseReceipt"
import type { UseFormSetValue } from "react-hook-form"
import type { TransactionFields } from "@/lib/forms/transactionSchema"
import type { components } from "@/lib/api/schema"

type CategoryItem = components["schemas"]["CategoryItem"]

interface Props {
  setValue: UseFormSetValue<TransactionFields>
  allCategories: CategoryItem[]
  onFillChange: (filled: Set<string>) => void
  onError: (msg: string | null) => void
}

export function ReceiptUpload({ setValue, allCategories, onFillChange, onError }: Props) {
  const parseReceipt = useParseReceipt()
  const fileInputRef = useRef<HTMLInputElement>(null)

  function handleReceiptFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    onError(null)
    parseReceipt.mutate(file, {
      onSuccess: (draft) => {
        const filled = new Set<string>()
        if (draft.amount)   { setValue("amount", draft.amount);                                        filled.add("amount") }
        if (draft.currency) { setValue("currency", draft.currency as "JPY"|"USD"|"EUR"|"GBP");         filled.add("currency") }
        if (draft.date)     { setValue("date", draft.date);                                            filled.add("date") }
        if (draft.merchant) { setValue("merchant", draft.merchant);                                    filled.add("merchant") }
        if (draft.notes)    { setValue("notes", draft.notes);                                          filled.add("notes") }
        if (draft.suggested_category_code) {
          const code = draft.suggested_category_code.toLowerCase()
          const match = allCategories.find(
            (c) => c.parent_id !== null && c.name.toLowerCase().includes(code)
          )
          if (match) { setValue("category_id", match.id); filled.add("category_id") }
        }
        onFillChange(filled)
      },
      onError: (err) => onError(err instanceof Error ? err.message : "Receipt parse failed"),
    })
  }

  return (
    <>
      <button
        type="button"
        title="Scan receipt"
        disabled={parseReceipt.isPending}
        onClick={() => fileInputRef.current?.click()}
        className={`flex items-center justify-center w-10 h-10 rounded-[var(--radius-md)] border transition-colors shrink-0
          ${parseReceipt.isPending
            ? "border-[var(--accent)] bg-[var(--accent)]/10 animate-pulse"
            : "border-[var(--rule-strong)] bg-[var(--surface)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
          } text-[var(--text-3)]`}
      >
        {parseReceipt.isPending ? (
          <span className="text-[10px] font-mono text-[var(--accent)]">…</span>
        ) : (
          <span className="text-base leading-none select-none">📷</span>
        )}
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*,application/pdf"
        capture="environment"
        className="hidden"
        onChange={handleReceiptFile}
      />
    </>
  )
}
