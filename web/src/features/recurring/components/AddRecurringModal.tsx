"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createRecurringRule } from "../api";
import type { CreateRecurringRulePayload, Recurrence, TxType } from "../types";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

const schema = z.object({
  type: z.enum(["income", "expense"]),
  amount: z.string().min(1, "Required"),
  currency: z.string().min(1, "Required"),
  merchant: z.string().optional(),
  recurrence: z.enum(["weekly", "monthly", "yearly"]),
  day_of_week: z.string().optional(),
  day_of_month: z.string().optional(),
  month: z.string().optional(),
  start_date: z.string().min(1, "Required"),
  end_date: z.string().optional(),
});

type Fields = z.infer<typeof schema>;

interface Props {
  onClose: () => void;
  onSuccess: () => void;
}

export function AddRecurringModal({ onClose, onSuccess }: Props) {
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isPending, setIsPending] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<Fields>({
    resolver: zodResolver(schema),
    defaultValues: {
      type: "expense",
      currency: "USD",
      recurrence: "monthly",
      start_date: new Date().toISOString().slice(0, 10),
    },
  });

  const recurrence = watch("recurrence");
  const type = watch("type");

  async function onSubmit(data: Fields) {
    setGeneralError(null);
    setIsPending(true);
    try {
      const payload: CreateRecurringRulePayload = {
        amount: data.amount,
        currency: data.currency,
        type: data.type as TxType,
        recurrence: data.recurrence as Recurrence,
        start_date: data.start_date,
      };

      if (data.merchant) payload.merchant = data.merchant;
      if (data.end_date) payload.end_date = data.end_date;

      if (data.recurrence === "weekly" && data.day_of_week !== undefined) {
        payload.day_of_week = Number(data.day_of_week);
      }
      if (data.recurrence === "monthly" && data.day_of_month !== undefined) {
        payload.day_of_month = Number(data.day_of_month);
      }
      if (data.recurrence === "yearly") {
        if (data.day_of_month !== undefined) payload.day_of_month = Number(data.day_of_month);
        if (data.month !== undefined) payload.month = Number(data.month);
      }

      await createRecurringRule(payload);
      onSuccess();
    } catch (err: unknown) {
      const e = err as Record<string, unknown>;
      if (e?.detail && Array.isArray(e.detail)) {
        setGeneralError(e.detail.map((d: { msg: string }) => d.msg).join(", "));
      } else if (e?.detail && typeof e.detail === "string") {
        setGeneralError(e.detail);
      } else {
        setGeneralError("Something went wrong");
      }
    } finally {
      setIsPending(false);
    }
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-[560px] bg-[var(--bg)] border-[var(--rule-strong)]">
        <DialogHeader>
          <DialogTitle className="font-serif text-[22px] font-medium text-[var(--text)]">
            Add recurring rule
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5 pt-2">
          {/* Type toggle */}
          <div className="flex border border-[var(--rule-strong)] rounded-[var(--radius-sm)] overflow-hidden">
            {(["expense", "income"] as const).map((t) => (
              <button key={t} type="button" onClick={() => setValue("type", t)}
                className={`flex-1 py-2 text-xs font-mono transition-colors
                  ${type === t
                    ? t === "income" ? "bg-[var(--surface)] text-[var(--income)]" : "bg-[var(--surface)] text-[var(--text)]"
                    : "text-[var(--text-3)]"}`}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>

          {/* Amount + currency */}
          <div className="flex gap-2">
            <div className="flex-1">
              <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Amount</Label>
              <Input {...register("amount")} placeholder="0"
                className="font-mono text-[28px] bg-transparent border-[var(--rule-strong)]" />
              {errors.amount && <p className="text-[var(--danger)] text-xs mt-1">{errors.amount.message}</p>}
            </div>
            <div className="w-24">
              <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Currency</Label>
              <select {...register("currency")}
                className="w-full h-10 px-3 bg-transparent border border-[var(--rule-strong)] rounded text-sm text-[var(--text)] font-mono">
                {["USD", "JPY", "EUR", "GBP"].map((c) => <option key={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {/* Merchant */}
          <div>
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Merchant</Label>
            <Input {...register("merchant")} placeholder="e.g. Netflix"
              className="bg-transparent border-[var(--rule-strong)]" />
          </div>

          {/* Recurrence */}
          <div>
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Recurrence</Label>
            <select {...register("recurrence")}
              className="w-full h-10 px-3 bg-transparent border border-[var(--rule-strong)] rounded text-sm text-[var(--text)]">
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>

          {/* Dynamic day field */}
          {recurrence === "weekly" && (
            <div>
              <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Day of week</Label>
              <select {...register("day_of_week")}
                className="w-full h-10 px-3 bg-transparent border border-[var(--rule-strong)] rounded text-sm text-[var(--text)]">
                {WEEKDAYS.map((d, i) => (
                  <option key={d} value={i}>{d}</option>
                ))}
              </select>
            </div>
          )}

          {recurrence === "monthly" && (
            <div>
              <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Day of month (1–28)</Label>
              <Input {...register("day_of_month")} type="number" min={1} max={28} placeholder="1"
                className="bg-transparent border-[var(--rule-strong)] font-mono" />
            </div>
          )}

          {recurrence === "yearly" && (
            <div className="flex gap-2">
              <div className="w-40">
                <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Month</Label>
                <select {...register("month")}
                  className="w-full h-10 px-3 bg-transparent border border-[var(--rule-strong)] rounded text-sm text-[var(--text)]">
                  {MONTHS.map((m, i) => (
                    <option key={m} value={i + 1}>{m}</option>
                  ))}
                </select>
              </div>
              <div className="flex-1">
                <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Day (1–28)</Label>
                <Input {...register("day_of_month")} type="number" min={1} max={28} placeholder="1"
                  className="bg-transparent border-[var(--rule-strong)] font-mono" />
              </div>
            </div>
          )}

          {/* Start date */}
          <div>
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">Start date</Label>
            <Input type="date" {...register("start_date")}
              className="bg-transparent border-[var(--rule-strong)] font-mono" />
            {errors.start_date && <p className="text-[var(--danger)] text-xs mt-1">{errors.start_date.message}</p>}
          </div>

          {/* End date */}
          <div>
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest">End date (optional)</Label>
            <Input type="date" {...register("end_date")}
              className="bg-transparent border-[var(--rule-strong)] font-mono" />
          </div>

          {/* General error */}
          {generalError && (
            <p className="text-[var(--danger)] text-xs">{generalError}</p>
          )}

          <Button type="submit" disabled={isPending}
            className="w-full bg-[var(--accent)] text-[var(--fab-fg)]">
            {isPending ? "Saving…" : "Save rule"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
