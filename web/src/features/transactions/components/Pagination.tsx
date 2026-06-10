"use client"
import { useRouter, useSearchParams } from "next/navigation"

export function Pagination({ nextCursor }: { nextCursor: string | null }) {
  const router = useRouter()
  const sp = useSearchParams()

  function older() {
    if (!nextCursor) return
    const p = new URLSearchParams(sp.toString())
    p.set("cursor", nextCursor)
    router.push(`/transactions?${p}`)
  }

  function newer() {
    const p = new URLSearchParams(sp.toString())
    p.delete("cursor")
    router.push(`/transactions?${p}`)
  }

  const hasCursor = !!sp.get("cursor")

  return (
    <div className="flex justify-between items-center mt-7 pt-4 font-mono text-xs text-[var(--text-3)]">
      <button onClick={newer} disabled={!hasCursor} className="hover:text-[var(--text)] disabled:opacity-30">← newer</button>
      <button onClick={older} disabled={!nextCursor}
        className="hover:text-[var(--text)] disabled:opacity-30">
        older →
      </button>
    </div>
  )
}
