"use client"
import { useState, useEffect } from "react"
import { useParseText } from "../hooks/useParseText"
import type { UseFormSetValue } from "react-hook-form"
import type { TransactionFields } from "@/lib/forms/transactionSchema"

interface Props {
  setValue: UseFormSetValue<TransactionFields>
  onFillChange: (filled: Set<string>, lowConf: Set<string>) => void
}

export function ParseTextStrip({ setValue, onFillChange }: Props) {
  const parseText = useParseText()
  const [aiInput, setAiInput] = useState("")

  useEffect(() => {
    if (aiInput.length < 3) {
      onFillChange(new Set(), new Set())
      return
    }
    const t = setTimeout(async () => {
      try {
        const draft = await parseText.mutateAsync(aiInput)
        const filled = new Set<string>()
        const lowConf = new Set<string>(draft.low_confidence_fields)

        if (draft.amount)                { setValue("amount", draft.amount);                                              filled.add("amount") }
        if (draft.currency)              { setValue("currency", draft.currency as "JPY"|"USD"|"EUR"|"GBP");               filled.add("currency") }
        if (draft.date)                  { setValue("date", draft.date);                                                  filled.add("date") }
        if (draft.transaction_type)      { setValue("type", draft.transaction_type.toUpperCase() as "EXPENSE"|"INCOME");  filled.add("type") }
        if (draft.suggested_category_id) { setValue("category_id", draft.suggested_category_id);                         filled.add("category_id") }
        if (draft.merchant)              { setValue("merchant", draft.merchant);                                          filled.add("merchant") }

        onFillChange(filled, lowConf)
      } catch {
        // soft-fail
      }
    }, 700)
    return () => clearTimeout(t)
  }, [aiInput]) // eslint-disable-line react-hooks/exhaustive-deps

  function handleClear() {
    setAiInput("")
    parseText.reset()
    onFillChange(new Set(), new Set())
  }

  return (
    <div className={`flex-1 flex items-center gap-2 px-3 py-2 rounded-[var(--radius-md)] border
      ${parseText.isPending
        ? "border-[var(--accent)] bg-[var(--accent)]/10"
        : "border-[var(--rule-strong)] bg-[var(--surface)]"}`}>
      <span className="text-[var(--accent)] text-sm select-none">✦</span>
      <input
        value={aiInput}
        onChange={(e) => setAiInput(e.target.value)}
        placeholder="coffee 600 yesterday…"
        className="flex-1 bg-transparent border-none outline-none text-sm text-[var(--text)] placeholder:text-[var(--text-3)] font-sans"
      />
      {parseText.isPending && (
        <span className="font-mono text-[10px] text-[var(--text-3)] animate-pulse">parsing…</span>
      )}
      {!parseText.isPending && !aiInput && (
        <span
          title="Type a description like 'coffee 600 yesterday' to auto-fill the form"
          className="font-mono text-[10px] text-[var(--text-3)] uppercase tracking-widest bg-[var(--surface)] border border-[var(--rule-strong)] px-1.5 py-0.5 rounded cursor-help"
        >
          auto-fill
        </span>
      )}
      {aiInput && (
        <button
          type="button"
          onClick={handleClear}
          className="text-[var(--text-3)] hover:text-[var(--text)] text-sm leading-none"
        >
          ×
        </button>
      )}
    </div>
  )
}
