import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatAmount(raw: string): string {
  const n = parseFloat(raw)
  return isNaN(n) ? raw : n.toString()
}
