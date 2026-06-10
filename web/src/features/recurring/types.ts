import type { components } from "@/lib/api/schema"

export type RecurringRuleStatus = "active" | "paused"
export type Recurrence = "weekly" | "monthly" | "yearly"
export type TxType = "income" | "expense"

type RecurringRuleItem = components["schemas"]["RecurringRuleItem"]

export type RecurringRule = Omit<RecurringRuleItem, "type" | "recurrence" | "status"> & {
  type: TxType
  recurrence: Recurrence
  status: RecurringRuleStatus
}

export type CreateRecurringRulePayload = components["schemas"]["CreateRecurringRuleRequest"]
export type UpdateRecurringRulePayload = components["schemas"]["UpdateRecurringRuleRequest"]
