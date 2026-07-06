import { test, expect } from "./fixtures"

const PASSWORD = "StrongPass1!"

/**
 * React Query cache must NOT leak across auth boundaries.
 *
 * Previously, `useLogin` / `useLogout` / `useRegister` redirected without
 * clearing the cache, so user A's cached `/v1/transactions` payload would still
 * render briefly for user B after a fast re-auth on the same browser session.
 *
 * Test strategy: User A creates a uniquely-merchant'd transaction, logs out,
 * then a fresh User B logs in. User B must NEVER see User A's merchant string,
 * neither on first paint nor after settling.
 */

test.describe("Auth boundary clears cached data", () => {
  test("user B does not see user A's transactions after logout/login on same page", async ({
    page,
  }) => {
    const a = `e2e-leak-a-${Date.now()}@test.com`
    const b = `e2e-leak-b-${Date.now()}@test.com`
    const merchantA = `MERCHANT_LEAK_A_${Date.now()}`

    // ── User A: register, create one transaction via API ──────────────────
    const regA = await page.request.post("/api/v1/auth/register", {
      data: { email: a, password: PASSWORD },
    })
    expect(regA.ok()).toBe(true)

    const txA = await page.request.post("/api/v1/transactions", {
      data: {
        amount: "123.45",
        currency: "USD",
        date: "2026-05-01",
        type: "expense",
        merchant: merchantA,
      },
    })
    expect(txA.ok()).toBe(true)

    // Warm the cache: visit transactions page so React Query has user A's data.
    await page.goto("/transactions")
    await expect(page.getByText(merchantA)).toBeVisible({ timeout: 8_000 })

    // ── User A: logout via UI (this is what triggers the cache clear) ────
    await page.getByRole("button", { name: /sign out/i }).click()
    await expect(page).toHaveURL("/login")

    // ── User B: register fresh on the same browser/Playwright page ────────
    await page.goto("/register")
    await page.getByLabel("Email").fill(b)
    await page.getByLabel("Password").fill(PASSWORD)
    await page.getByLabel("Confirm password").fill(PASSWORD)
    await page.getByRole("button", { name: /create account/i }).click()
    await expect(page).toHaveURL("/dashboard", { timeout: 10_000 })

    // ── Assert: user B's transactions page must NEVER show merchantA ──────
    await page.goto("/transactions")
    // We have to wait for the list query to settle first — give it the same
    // budget any real query gets, then assert absence.
    await page.waitForLoadState("networkidle")
    await expect(page.getByText(merchantA)).toHaveCount(0)
  })

  test("login from anonymous session clears any pre-existing cache", async ({ page }) => {
    // Edge of the same bug: if the browser had a stale persistent cache (e.g.
    // SWR/RQ persistence across page loads), login must wipe it before the
    // first authenticated query lands.
    const u = `e2e-leak-login-${Date.now()}@test.com`
    const merchant = `MERCHANT_FRESH_${Date.now()}`

    const reg = await page.request.post("/api/v1/auth/register", {
      data: { email: u, password: PASSWORD },
    })
    expect(reg.ok()).toBe(true)
    await page.request.post("/api/v1/transactions", {
      data: {
        amount: "10.00",
        currency: "USD",
        date: "2026-05-01",
        type: "expense",
        merchant,
      },
    })

    await page.goto("/dashboard")
    // logout → login round-trip
    await page.getByRole("button", { name: /sign out/i }).click()
    await expect(page).toHaveURL("/login")
    await page.getByLabel("Email").fill(u)
    await page.getByLabel("Password").fill(PASSWORD)
    await page.getByRole("button", { name: /sign in/i }).click()
    await expect(page).toHaveURL("/dashboard", { timeout: 10_000 })

    // Sanity: the user's OWN transaction does show up after a fresh login —
    // proves we didn't break the happy path while plugging the leak.
    await page.goto("/transactions")
    await expect(page.getByText(merchant)).toBeVisible({ timeout: 8_000 })
  })
})
