"use client"
import { useState } from "react"
import { useCategories } from "@/features/transactions/hooks/useTransactions"
import { useCreateCategory } from "../hooks/useCreateCategory"
import { PageHead } from "@/components/shell/PageHead"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

const PRESET_COLORS = [
  "#c9a96e", "#6b9e7a", "#b56a5e", "#7a7060",
  "#5e8ab5", "#a96eb5", "#6eb5a9", "#b5a96e",
]

type CategoryItem = {
  id: string
  name: string
  icon: string | null
  color: string | null
  is_system: boolean
  parent_id: string | null
  type: string
}

function HierarchySection({
  groups,
  allCategories,
  dimmed = false,
}: {
  groups: CategoryItem[]
  allCategories: CategoryItem[]
  dimmed?: boolean
}) {
  return (
    <div className="border border-[var(--rule)] rounded-[var(--radius-md)] divide-y divide-[var(--rule)]">
      {groups.map((group) => {
        const leaves = allCategories.filter((c) => c.parent_id === group.id)
        return (
          <div key={group.id} className={dimmed ? "bg-[var(--bg)]" : undefined}>
            <div className="flex items-center gap-3 px-4 py-3">
              <span
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: group.color ?? "var(--text-3)" }}
              />
              <span className="font-serif text-[15px] font-medium text-[var(--text)]">{group.name}</span>
              <span className={`font-mono text-[10px] ml-1 px-1 rounded ${group.type === "income" ? "text-[var(--income)] bg-[var(--income)]/10" : "text-[var(--text-3)] bg-[var(--surface)]"}`}>
                {group.type}
              </span>
              {dimmed && (
                <span className="font-mono text-[10px] text-[var(--text-3)] ml-auto">system</span>
              )}
            </div>
            {leaves.length > 0 && (
              <div className="divide-y divide-[var(--rule)] border-t border-[var(--rule)]">
                {leaves.map((leaf) => (
                  <div key={leaf.id} className="flex items-center gap-3 pl-10 pr-4 py-2.5">
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{ backgroundColor: leaf.color ?? "var(--text-3)" }}
                    />
                    <span className="font-serif text-[14px] font-medium text-[var(--text-2)]">{leaf.name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function CategoriesView() {
  const { data: categoriesData, isLoading, isError } = useCategories()
  const createCategory = useCreateCategory()
  const [name, setName] = useState("")
  const [color, setColor] = useState(PRESET_COLORS[0])
  const [type, setType] = useState<"expense" | "income">("expense")
  const [parentId, setParentId] = useState<string>("")

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-10 bg-[var(--surface)] rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (isError) {
    return <p className="font-mono text-sm text-[var(--danger)]">Failed to load categories.</p>
  }

  const allCategories: CategoryItem[] = categoriesData?.items ?? []
  const allGroups = allCategories.filter((c) => c.parent_id === null)

  // Parent picker shows all groups filtered by selected type
  const parentOptions = allGroups.filter((g) => g.type === type)

  const userGroups = allGroups.filter((c) => !c.is_system)
  const systemGroups = allGroups.filter((c) => c.is_system)

  // Derived: the selected parent group's type (if any) locks the type selector
  const selectedParent = parentId ? allGroups.find((g) => g.id === parentId) : null

  function handleTypeChange(t: "expense" | "income") {
    setType(t)
    setParentId("") // clear parent when type changes
  }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    createCategory.mutate(
      {
        name: name.trim(),
        type: selectedParent ? selectedParent.type : type,
        parent_id: parentId || null,
        color,
      },
      {
        onSuccess: () => {
          setName("")
          setColor(PRESET_COLORS[0])
          setType("expense")
          setParentId("")
        },
      },
    )
  }

  return (
    <div>
      <PageHead crumb="CATEGORIES" title="Categories" />

      {/* Create new */}
      <form
        onSubmit={handleCreate}
        className="space-y-4 mb-10 p-5 border border-[var(--rule)] rounded-[var(--radius-md)]"
      >
        <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)]">New category</p>

        {/* Type toggle */}
        <div>
          <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest mb-1 block">Type</Label>
          <div className="flex border border-[var(--rule-strong)] rounded-[var(--radius-sm)] overflow-hidden w-48">
            {(["expense", "income"] as const).map((t) => (
              <button
                key={t}
                type="button"
                disabled={!!selectedParent}
                onClick={() => handleTypeChange(t)}
                className={`flex-1 py-1.5 text-xs font-mono transition-colors
                  ${type === t
                    ? t === "income" ? "bg-[var(--surface)] text-[var(--income)]" : "bg-[var(--surface)] text-[var(--text)]"
                    : "text-[var(--text-3)]"}
                  ${selectedParent ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Parent group (optional — if set, creates a leaf) */}
        <div>
          <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest mb-1 block">
            Parent group <span className="normal-case font-sans text-[var(--text-3)]">(optional — creates sub-category)</span>
          </Label>
          <Select
            value={parentId}
            onValueChange={(v: string | null) => {
              setParentId(v ?? "")
              if (v) {
                const g = allGroups.find((g) => g.id === v)
                if (g) setType(g.type as "expense" | "income")
              }
            }}
          >
            <SelectTrigger className="w-full h-9 text-sm bg-transparent border-[var(--rule-strong)]">
              <SelectValue>
                {!parentId
                  ? <span className="text-[var(--text-3)]">— none (creates group) —</span>
                  : (allGroups.find(g => g.id === parentId)?.name ?? "— none (creates group) —")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">— none (creates group) —</SelectItem>
              {parentOptions.map((g) => (
                <SelectItem key={g.id} value={g.id}>{g.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Name + color + submit */}
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest mb-1 block">Name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Dining"
              className="bg-transparent border-[var(--rule-strong)] text-[var(--text)]"
            />
          </div>
          <div>
            <Label className="text-[var(--text-3)] text-xs uppercase tracking-widest mb-1 block">Color</Label>
            <div className="flex gap-1.5 flex-wrap max-w-[180px]">
              {PRESET_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className={`w-6 h-6 rounded-full border-2 transition-all ${color === c ? "border-[var(--text)] scale-110" : "border-transparent"}`}
                  style={{ backgroundColor: c }}
                />
              ))}
            </div>
          </div>
          <Button
            type="submit"
            disabled={createCategory.isPending || !name.trim()}
            className="bg-[var(--accent)] text-[var(--fab-fg)]"
          >
            {createCategory.isPending ? "Creating…" : "Create"}
          </Button>
        </div>

        {createCategory.isError && (
          <p className="font-mono text-xs text-[var(--danger)]">
            {(createCategory.error as { message?: string })?.message ?? "Failed to create category"}
          </p>
        )}
      </form>

      {/* User categories */}
      {userGroups.length > 0 && (
        <section className="mb-8">
          <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-4">Your categories</p>
          <HierarchySection groups={userGroups} allCategories={allCategories} />
        </section>
      )}

      {/* System categories */}
      {systemGroups.length > 0 && (
        <section>
          <p className="font-mono text-[11px] uppercase tracking-widest text-[var(--text-3)] mb-4">System categories</p>
          <HierarchySection groups={systemGroups} allCategories={allCategories} dimmed />
        </section>
      )}
    </div>
  )
}
