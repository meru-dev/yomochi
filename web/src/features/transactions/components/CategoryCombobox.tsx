"use client"
import { useId, useState } from "react"
import type { components } from "@/lib/api/schema"
import { ChevronDownIcon } from "lucide-react"
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover"
import {
  Command, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem,
} from "@/components/ui/command"
import { cn } from "@/lib/utils"

type CategoryItem = components["schemas"]["CategoryItem"]

export interface CategoryGroup {
  groupName: string
  items: CategoryItem[]
}

interface Props {
  value: string
  onChange: (value: string) => void
  groups: CategoryGroup[]
  allCategories: CategoryItem[]
  className?: string
}

export function CategoryCombobox({ value, onChange, groups, allCategories, className }: Props) {
  const [open, setOpen] = useState(false)
  const selectedName = allCategories.find(c => c.id === value)?.name
  const contentId = useId()

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            type="button"
            role="combobox"
            aria-haspopup="listbox"
            aria-expanded={open}
            aria-controls={contentId}
            className={cn(
              "flex w-full items-center justify-between gap-2 h-10 px-3 text-sm border rounded-lg transition-colors bg-transparent",
              className
            )}
          />
        }
      >
        <span className={selectedName ? "text-[var(--text)]" : "text-[var(--text-3)]"}>
          {selectedName ?? "— none —"}
        </span>
        <ChevronDownIcon className="size-4 text-[var(--text-3)] shrink-0 pointer-events-none" />
      </PopoverTrigger>
      <PopoverContent id={contentId} side="bottom" align="start" sideOffset={4} className="w-(--anchor-width) p-0">
        <Command>
          <CommandInput placeholder="Search category…" />
          <CommandList>
            <CommandEmpty>No categories found.</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value="none"
                data-checked={!value}
                onSelect={() => { onChange(""); setOpen(false) }}
              >
                — none —
              </CommandItem>
            </CommandGroup>
            {groups.map(({ groupName, items }) => (
              <CommandGroup key={groupName} heading={groupName}>
                {items.map((c) => (
                  <CommandItem
                    key={c.id}
                    value={c.name}
                    data-checked={value === c.id}
                    onSelect={() => { onChange(c.id); setOpen(false) }}
                  >
                    {c.name}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
