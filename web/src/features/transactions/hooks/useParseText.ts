"use client"
import { useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api/client"


export interface ParsedDraft {
  amount: string | null
  currency: string | null
  merchant: string | null
  transaction_type: string | null     // "expense" | "income" | null
  date: string | null                 // ISO date "YYYY-MM-DD"
  suggested_category_id: string | null
  confidence: number                  // 0–1
  requires_review: boolean
  low_confidence_fields: string[]     // field names that are uncertain
}

export function useParseText() {
  return useMutation({
    mutationFn: async (text: string): Promise<ParsedDraft> => {
      const { data, error } = await api.POST("/api/v1/transactions/parse-text", {
        body: { text },
      })
      if (error) throw error
      return data as ParsedDraft
    },
  })
}
