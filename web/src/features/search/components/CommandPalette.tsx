"use client"
import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import {
  Command,
  CommandInput,
  CommandList,
  CommandItem,
  CommandEmpty,
} from "@/components/ui/command"
import { useUIStore } from "@/lib/store/ui"
import { useSearch } from "../hooks/useSearch"
import { useDebouncedValue } from "@/hooks/useDebouncedValue"

export function CommandPalette() {
  const { paletteOpen, closePalette, setFocusedTxIds } = useUIStore()
  const [query, setQuery] = useState("")
  const debouncedQuery = useDebouncedValue(query, 400)
  const search = useSearch(debouncedQuery)
  const router = useRouter()

  useEffect(() => {
    if (!paletteOpen) {
      setQuery("")
    }
  }, [paletteOpen])

  function selectResult(id: string) {
    setFocusedTxIds([id])
    router.push(`/transactions?focus=${id}`)
    closePalette()
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const results: any[] = search.data?.items ?? []

  return (
    <Dialog open={paletteOpen} onOpenChange={(o) => !o && closePalette()}>
      <DialogContent className="p-0 max-w-[600px] bg-[var(--bg)] border-[var(--rule-strong)] shadow-[0_24px_60px_rgba(0,0,0,0.32)]">
        <Command className="bg-transparent" shouldFilter={false}>
          <CommandInput
            value={query}
            onValueChange={setQuery}
            placeholder="Search transactions…"
            className="font-sans text-[17px] border-b border-[var(--rule)] h-14 px-5"
          />
          <CommandList className="max-h-[400px]">
            {search.isFetching && (
              <p className="text-center py-6 text-sm text-[var(--text-3)]">Searching…</p>
            )}
            {!search.isFetching && results.length === 0 && debouncedQuery.length >= 3 && (
              <CommandEmpty className="py-6 text-sm text-[var(--text-3)]">
                No results found.
              </CommandEmpty>
            )}
            {results.map((tx) => (
              <CommandItem key={tx.id} onSelect={() => selectResult(tx.id)}
                className="px-5 py-3 cursor-pointer">
                <div className="flex items-center justify-between w-full">
                  <div>
                    <p className="font-serif text-[15px] text-[var(--text)]">{tx.merchant ?? "—"}</p>
                    <p className="font-mono text-xs text-[var(--text-3)]">{tx.date}</p>
                  </div>
                  <span className="font-mono text-sm text-[var(--text-2)]">
                    {tx.currency} {tx.amount}
                  </span>
                </div>
              </CommandItem>
            ))}
          </CommandList>
          {results.length > 0 && (
            <div className="border-t border-[var(--rule)] px-5 py-2 font-mono text-xs text-[var(--text-3)]">
              {results.length} result{results.length !== 1 ? "s" : ""}
            </div>
          )}
        </Command>
      </DialogContent>
    </Dialog>
  )
}
