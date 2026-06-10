import { api } from "@/lib/api/client"
import type {
  RecurringRule,
  CreateRecurringRulePayload,
  UpdateRecurringRulePayload,
} from "./types"

const BASE = "/api/v1/recurring-rules" as const

export async function listRecurringRules(): Promise<{ items: RecurringRule[] }> {
  const { data, error } = await api.GET(BASE)
  if (error) throw error
  if (!data) throw new Error("listRecurringRules returned no data")
  return { items: data.items as RecurringRule[] }
}

export async function createRecurringRule(
  payload: CreateRecurringRulePayload,
): Promise<{ id: string }> {
  const { data, error } = await api.POST(BASE, { body: payload })
  if (error) throw error
  if (!data) throw new Error("createRecurringRule returned no data")
  return data
}

export async function updateRecurringRule(
  id: string,
  patch: UpdateRecurringRulePayload,
): Promise<RecurringRule> {
  const { data, error } = await api.PATCH("/api/v1/recurring-rules/{rule_id}", {
    params: { path: { rule_id: id } },
    body: patch,
  })
  if (error) throw error
  if (!data) throw new Error("updateRecurringRule returned no data")
  return data as RecurringRule
}

export async function deleteRecurringRule(id: string): Promise<void> {
  const { error } = await api.DELETE("/api/v1/recurring-rules/{rule_id}", {
    params: { path: { rule_id: id } },
  })
  if (error) throw error
}
