export const keys = {
  transactions: {
    all: () => ["transactions"] as const,
    list: (filters?: Record<string, unknown>) =>
      ["transactions", "list", filters] as const,
    recent: () => ["transactions", "recent"] as const,
    detail: (id: string) => ["transactions", "detail", id] as const,
  },
  reports: {
    summary: (year: number, month: number) =>
      ["reports", "summary", year, month] as const,
    trend: (currency: string, months: number, txType?: string, granularity?: string) =>
      ["reports", "trend", currency, months, txType, granularity] as const,
  },
  insights: {
    all: () => ["insights"] as const,
    list: () => ["insights", "list"] as const,
    detail: (id: string) => ["insights", "detail", id] as const,
    byPeriod: (period: string, year: number, month: number) =>
      ["insights", "byPeriod", period, year, month] as const,
  },
  categories: {
    list: () => ["categories", "list"] as const,
  },
  recurringRules: {
    list: () => ["recurring-rules"] as const,
  },
  search: {
    result: (query: string) => ["search", query] as const,
  },
  chat: {
    history: () => ["chat", "history"] as const,
  },
  alerts: {
    unreadCount: () => ["alerts", "unread-count"] as const,
    list: () => ["alerts", "list"] as const,
  },
  sessions: {
    list: () => ["sessions", "list"] as const,
  },
} as const
