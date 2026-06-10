"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listRecurringRules, updateRecurringRule, deleteRecurringRule } from "../api";
import { RecurringRuleCard } from "./RecurringRuleCard";
import { AddRecurringModal } from "./AddRecurringModal";
import { keys } from "@/lib/query/keys";
import { useUIStore } from "@/lib/store/ui"
import { useConfirm } from "@/hooks/useConfirm";

export function RecurringList() {
  const [showAdd, setShowAdd] = useState(false);
  const qc = useQueryClient();
  const { showToast } = useUIStore()
  const { confirm, confirmPortal } = useConfirm();

  const { data, isLoading, isError } = useQuery({
    queryKey: keys.recurringRules.list(),
    queryFn: listRecurringRules,
  });

  type CachedRules = { items: { id: string; [k: string]: unknown }[] } | undefined;

  const mutate = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Record<string, unknown> }) =>
      updateRecurringRule(id, patch),
    onMutate: async ({ id, patch }) => {
      await qc.cancelQueries({ queryKey: keys.recurringRules.list() });
      const prev = qc.getQueryData<CachedRules>(keys.recurringRules.list());
      qc.setQueryData<CachedRules>(keys.recurringRules.list(), (old) =>
        old
          ? { ...old, items: old.items.map((r) => (r.id === id ? { ...r, ...patch } : r)) }
          : old,
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.recurringRules.list(), ctx.prev);
      showToast({ message: "Failed to update rule.", ttl: 3000 });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.recurringRules.list() }),
  });

  const remove = useMutation({
    mutationFn: deleteRecurringRule,
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: keys.recurringRules.list() });
      const prev = qc.getQueryData<CachedRules>(keys.recurringRules.list());
      qc.setQueryData<CachedRules>(keys.recurringRules.list(), (old) =>
        old ? { ...old, items: old.items.filter((r) => r.id !== id) } : old,
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.recurringRules.list(), ctx.prev);
      showToast({ message: "Failed to delete rule.", ttl: 3000 });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.recurringRules.list() }),
  });

  if (isError) {
    return <p className="font-mono text-sm text-[var(--danger)]">Failed to load recurring rules.</p>;
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="h-20 bg-[var(--surface)] rounded-[var(--radius-md)] animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-serif text-[22px] font-medium text-[var(--text)]">Recurring</h2>
        <button
          onClick={() => setShowAdd(true)}
          className="font-mono text-xs uppercase tracking-widest px-3 py-1.5 rounded-[var(--radius-sm)] bg-[var(--accent)] text-[var(--fab-fg)] hover:opacity-90 transition-opacity"
        >
          + Add
        </button>
      </div>

      {(data?.items ?? []).length === 0 ? (
        <p className="font-mono text-xs text-[var(--text-3)] uppercase tracking-widest">
          No recurring rules yet.
        </p>
      ) : (
        (data?.items ?? []).map((rule) => (
          <RecurringRuleCard
            key={rule.id}
            rule={rule}
            onPause={(id) => mutate.mutate({ id, patch: { status: "paused" } })}
            onResume={(id) => mutate.mutate({ id, patch: { status: "active" } })}
            onDelete={async (id) => {
              if (await confirm("Delete this rule? Past transactions will be kept."))
                remove.mutate(id);
            }}
          />
        ))
      )}

      {showAdd && (
        <AddRecurringModal
          onClose={() => setShowAdd(false)}
          onSuccess={() => {
            setShowAdd(false);
            qc.invalidateQueries({ queryKey: keys.recurringRules.list() });
          }}
        />
      )}
      {confirmPortal}
    </div>
  );
}
