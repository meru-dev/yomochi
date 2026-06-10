"use client";

import { RecurringRule } from "../types";
import { formatAmount } from "@/lib/utils";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function recurrenceLabel(rule: RecurringRule): string {
  if (rule.recurrence === "weekly" && rule.day_of_week !== null)
    return `Every ${WEEKDAYS[rule.day_of_week]}`;
  if (rule.recurrence === "monthly" && rule.day_of_month !== null)
    return `Monthly on day ${rule.day_of_month}`;
  if (rule.recurrence === "yearly" && rule.day_of_month !== null && rule.month !== null)
    return `Yearly on ${MONTHS[rule.month - 1]} ${rule.day_of_month}`;
  return rule.recurrence;
}

interface Props {
  rule: RecurringRule;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onDelete: (id: string) => void;
}

export function RecurringRuleCard({ rule, onPause, onResume, onDelete }: Props) {
  const isActive = rule.status === "active";
  const nextLabel = new Date(rule.next_fire_date + "T00:00:00").toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });

  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--rule-strong)] bg-[var(--surface)] p-4 flex items-center justify-between gap-4 shadow-sm">
      <div className="flex-1 min-w-0">
        <p className="font-serif text-[17px] text-[var(--text)] truncate">
          {rule.merchant ?? "—"}
        </p>
        <p className="font-mono text-xs text-[var(--text-2)] mt-0.5">
          {rule.type === "income" ? "+" : "−"}{formatAmount(rule.amount)} {rule.currency}
          {" · "}{recurrenceLabel(rule)}
        </p>
        <p className="font-mono text-[11px] text-[var(--text-3)] mt-1">
          Next: {nextLabel}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className={`font-mono text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${
          isActive
            ? "bg-[var(--income)]/10 text-[var(--income)]"
            : "bg-[var(--surface)] text-[var(--text-3)] border border-[var(--rule-strong)]"
        }`}>
          {rule.status}
        </span>
        <button
          onClick={() => isActive ? onPause(rule.id) : onResume(rule.id)}
          className="font-mono text-xs text-[var(--text-2)] hover:text-[var(--text)] underline transition-colors"
        >
          {isActive ? "Pause" : "Resume"}
        </button>
        <button
          onClick={() => onDelete(rule.id)}
          className="font-mono text-xs text-[var(--danger)] hover:underline transition-colors"
        >
          Delete
        </button>
      </div>
    </div>
  );
}
