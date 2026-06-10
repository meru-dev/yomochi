"use client"
import { useMutation } from "@tanstack/react-query"

export interface ParsedReceiptDraft {
  merchant: string | null
  amount: string | null
  currency: string | null
  date: string | null
  suggested_category_code: string | null
  notes: string | null
}

export function useParseReceipt() {
  return useMutation({
    mutationFn: async (file: File): Promise<ParsedReceiptDraft> => {
      const form = new FormData()
      form.append("file", file)
      const res = await fetch("/api/v1/ingestion/parse-receipt", {
        method: "POST",
        body: form,
        credentials: "include",
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body?.error?.message ?? `Parse failed (${res.status})`)
      }
      return res.json() as Promise<ParsedReceiptDraft>
    },
  })
}
