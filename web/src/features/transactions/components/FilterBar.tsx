"use client"
import { useRouter, useSearchParams } from "next/navigation"

const TYPES = ["All", "Expense", "Income"] as const
const CURRENCIES = ["JPY", "USD", "EUR", "GBP"] as const

export function FilterBar() {
  const router = useRouter()
  const sp = useSearchParams()
  const activeType = sp.get("type") ?? "All"
  const activeCurrencies = sp.getAll("currency")

  function setType(t: string) {
    const p = new URLSearchParams(sp.toString())
    p.delete("cursor")
    if (t === "All") p.delete("type"); else p.set("type", t.toLowerCase())
    router.push(`/transactions?${p}`)
  }

  function toggleCurrency(c: string) {
    const p = new URLSearchParams(sp.toString())
    p.delete("cursor")
    const curr = p.getAll("currency")
    if (curr.includes(c)) {
      p.delete("currency")
      curr.filter((x) => x !== c).forEach((x) => p.append("currency", x))
    } else {
      p.append("currency", c)
    }
    router.push(`/transactions?${p}`)
  }

  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {TYPES.map((t) => (
        <button key={t} onClick={() => setType(t)}
          className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-colors
            ${activeType === (t === "All" ? "All" : t.toLowerCase())
              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
              : "border-[var(--rule-strong)] text-[var(--text-2)] hover:text-[var(--text)] hover:border-[var(--text-3)]"}`}>
          {t}
        </button>
      ))}
      {CURRENCIES.map((c) => (
        <button key={c} onClick={() => toggleCurrency(c)}
          className={`px-3 py-1.5 text-xs font-mono rounded-full border transition-colors
            ${activeCurrencies.includes(c)
              ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
              : "border-[var(--rule-strong)] text-[var(--text-2)] hover:text-[var(--text)] hover:border-[var(--text-3)]"}`}>
          {c === "JPY" ? "¥" : c === "USD" ? "$" : c === "EUR" ? "€" : "£"} {c}
        </button>
      ))}
    </div>
  )
}
