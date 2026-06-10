import { create } from "zustand"

export interface ToastSpec {
  id: string
  message: string
  meta?: string
  undo?: () => void
  ttl: number
}

export interface TxData {
  id: string
  date: string
  merchant: string | null
  notes: string | null
  category_id: string | null
  recurring_rule_id: string | null
  amount: string
  currency: string
  type: string
}

interface UIStore {
  addOpen: boolean
  paletteOpen: boolean
  focusedTxIds: string[]
  toasts: ToastSpec[]
  editingTx: TxData | null
  alertsOpen: boolean

  openAdd: () => void
  closeAdd: () => void
  togglePalette: () => void
  closePalette: () => void
  setFocusedTxIds: (ids: string[]) => void
  clearFocusedTxIds: () => void
  showToast: (spec: Omit<ToastSpec, "id">) => void
  dismissToast: (id: string) => void
  openEdit: (tx: TxData) => void
  closeEdit: () => void
  openAlerts: () => void
  closeAlerts: () => void
}

export const useUIStore = create<UIStore>((set) => ({
  addOpen: false,
  paletteOpen: false,
  focusedTxIds: [],
  toasts: [],
  editingTx: null,
  alertsOpen: false,

  openAdd: () => set({ addOpen: true }),
  closeAdd: () => set({ addOpen: false }),
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  closePalette: () => set({ paletteOpen: false }),
  setFocusedTxIds: (ids) => set({ focusedTxIds: ids }),
  clearFocusedTxIds: () => set({ focusedTxIds: [] }),
  showToast: (spec) =>
    set((s) => ({
      toasts: [...s.toasts, { ...spec, id: crypto.randomUUID() }],
    })),
  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  openEdit: (tx) => set({ editingTx: tx }),
  closeEdit: () => set({ editingTx: null }),
  openAlerts: () => set({ alertsOpen: true }),
  closeAlerts: () => set({ alertsOpen: false }),
}))
