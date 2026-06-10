"use client"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useUIStore } from "@/lib/store/ui"

export function useKeyboardShortcuts() {
  const router = useRouter()
  const { openAdd, togglePalette, closeAdd, closePalette } = useUIStore()

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement).tagName
      const inInput = ["INPUT", "TEXTAREA", "SELECT"].includes(tag)

      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        togglePalette()
        return
      }

      if (e.key === "Escape") {
        closeAdd()
        closePalette()
        return
      }

      if (inInput) return

      switch (e.key) {
        case "d": router.push("/dashboard"); break
        case "t": router.push("/transactions"); break
        case "i": {
          const now = new Date()
          const period = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`
          router.push(`/insights/monthly/${period}`)
          break
        }
        case "n": openAdd(); break
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [router, openAdd, togglePalette, closeAdd, closePalette])
}
