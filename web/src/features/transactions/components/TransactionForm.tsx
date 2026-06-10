"use client"
import type { ReactNode } from "react"
import type { UseFormReturn } from "react-hook-form"
import { Controller } from "react-hook-form"
import type { components } from "@/lib/api/schema"
import type { TransactionFields } from "@/lib/forms/transactionSchema"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { CategoryCombobox } from "./CategoryCombobox"

type CategoryItem = components["schemas"]["CategoryItem"]

export interface TransactionFormTopSlotProps {
  fieldClass: (name: string) => string
}

export interface TransactionFormProps {
  mode: "create" | "edit"
  form: UseFormReturn<TransactionFields>
  allCategories: CategoryItem[]
  onSubmit: (values: TransactionFields) => Promise<void> | void
  isSubmitting: boolean
  generalError: string | null
  /** Highlighted (AI-filled) field names — applies accent border. */
  aiFilledFields?: ReadonlySet<string>
  /** Low-confidence field names — applies warning border. Wins over aiFilledFields. */
  lowConfFields?: ReadonlySet<string>
  /** Optional row above the type toggle (used by Add modal for AI strip + receipt upload). */
  topSlot?: (props: TransactionFormTopSlotProps) => ReactNode
}

const EMPTY_SET: ReadonlySet<string> = new Set()

export function TransactionForm({
  mode,
  form,
  allCategories,
  onSubmit,
  isSubmitting,
  generalError,
  aiFilledFields = EMPTY_SET,
  lowConfFields = EMPTY_SET,
  topSlot,
}: TransactionFormProps) {
  const {
    register,
    handleSubmit,
    watch,
    setValue,
    control,
    formState: { errors },
  } = form

  const type = watch("type")

  function groupedLeaves(txType: string) {
    const typeFilter = txType.toLowerCase()
    const groupsById = new Map(
      allCategories.filter((c) => c.parent_id === null).map((c) => [c.id, c.name])
    )
    const leaves = allCategories.filter((c) => c.parent_id !== null && c.type === typeFilter)
    const grouped = new Map<string, { groupName: string; items: typeof leaves }>()
    for (const leaf of leaves) {
      const pid = leaf.parent_id!
      if (!grouped.has(pid)) grouped.set(pid, { groupName: groupsById.get(pid) ?? "Other", items: [] })
      grouped.get(pid)!.items.push(leaf)
    }
    return [...grouped.values()]
  }

  function fieldClass(name: string): string {
    if (lowConfFields.has(name)) return "border-[var(--warn)] bg-[var(--warn)]/10"
    if (aiFilledFields.has(name)) return "border-[var(--accent)] bg-[var(--accent)]/10"
    return "border-[var(--rule-strong)]"
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 pt-2">
      {topSlot?.({ fieldClass })}

      {/* Type toggle */}
      <div className="flex border border-[var(--rule-strong)] rounded-[var(--radius-sm)] overflow-hidden">
        {(["EXPENSE", "INCOME"] as const).map((t) => (
          <button key={t} type="button" onClick={() => { setValue("type", t); setValue("category_id", "") }}
            className={`flex-1 py-2 text-xs font-mono transition-colors
              ${type === t
                ? t === "INCOME" ? "bg-[var(--surface)] text-[var(--income)]" : "bg-[var(--surface)] text-[var(--text)]"
                : "text-[var(--text-3)]"}`}>
            {t.charAt(0) + t.slice(1).toLowerCase()}
          </button>
        ))}
      </div>

      {/* Amount + currency */}
      <div className="flex gap-2">
        <div className="flex-1">
          <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Amount</Label>
          <Input {...register("amount")} placeholder="0"
            className={`font-mono text-[28px] bg-transparent ${fieldClass("amount")}`} />
          {errors.amount && <p className="text-[var(--danger)] text-xs mt-1">{errors.amount.message}</p>}
        </div>
        <div className="w-24">
          <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Currency</Label>
          <Controller name="currency" control={control} render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger className={`w-full h-10 font-mono text-sm bg-transparent ${fieldClass("currency")}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {["JPY", "USD", "EUR", "GBP"].map((c) => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )} />
          {errors.currency && <p className="text-[var(--danger)] text-xs mt-1">{errors.currency.message}</p>}
        </div>
      </div>

      {/* Date */}
      <div>
        <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Date</Label>
        <Input type="date" {...register("date")}
          className={`bg-transparent font-mono ${fieldClass("date")}`} />
        {errors.date && <p className="text-[var(--danger)] text-xs mt-1">{errors.date.message}</p>}
      </div>

      {/* Merchant */}
      <div>
        <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Merchant</Label>
        <Input {...register("merchant")} placeholder="e.g. Starbucks"
          className={`bg-transparent ${fieldClass("merchant")}`} />
      </div>

      {/* Category */}
      <div>
        <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Category</Label>
        <Controller name="category_id" control={control} render={({ field }) => (
          <CategoryCombobox
            value={field.value ?? ""}
            onChange={field.onChange}
            groups={groupedLeaves(type)}
            allCategories={allCategories}
            className={fieldClass("category_id")}
          />
        )} />
        {errors.category_id && <p className="text-[var(--danger)] text-xs mt-1">{errors.category_id.message}</p>}
      </div>

      {/* Notes */}
      <div>
        <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Notes</Label>
        <Textarea {...register("notes")} rows={2}
          className={`bg-transparent resize-none ${fieldClass("notes")}`} />
      </div>

      {generalError && (
        <p className="text-[var(--danger)] text-xs">{generalError}</p>
      )}

      <Button type="submit" disabled={isSubmitting}
        className="w-full bg-[var(--accent)] text-[var(--fab-fg)]">
        {isSubmitting ? "Saving…" : mode === "create" ? "Save transaction" : "Save changes"}
      </Button>
    </form>
  )
}
