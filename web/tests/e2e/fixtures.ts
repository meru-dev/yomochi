import { test as base, expect } from "@playwright/test"
import type { Page } from "@playwright/test"

export { expect }

export const test = base.extend<{ authedPage: Page }>({
  authedPage: async ({ page }, use) => {
    const email = `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@test.com`
    const res = await page.request.post("/api/v1/auth/register", {
      data: { email, password: "StrongPass1!" },
    })
    if (!res.ok()) throw new Error(`Auth fixture: register failed ${res.status()} — ${await res.text()}`)
    await use(page)
  },
})
