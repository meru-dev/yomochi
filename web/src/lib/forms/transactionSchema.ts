import { z } from "zod"

export const transactionSchema = z.object({
  type: z.enum(["EXPENSE", "INCOME"]),
  amount: z.string().min(1, "Required"),
  currency: z.enum(["JPY", "USD", "EUR", "GBP"]),
  date: z.string().min(1, "Required"),
  merchant: z.string().optional(),
  notes: z.string().optional(),
  category_id: z.string().optional(),
})

export type TransactionFields = z.infer<typeof transactionSchema>
