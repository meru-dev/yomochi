import { test, expect } from "./fixtures"

const PASSWORD = "StrongPass1!"

test.describe("Auth flows", () => {
  test("login → dashboard redirect", async ({ page }) => {
    const email = `e2e-login-${Date.now()}@test.com`

    // Create account via API — reliable, no UI timing flakiness
    const res = await page.request.post("/api/v1/auth/register", {
      data: { email, password: PASSWORD },
    })
    expect(res.ok()).toBe(true)

    // Logout via UI (cookie was set by the register API call above)
    await page.goto("/dashboard")
    await page.getByRole("button", { name: /sign out/i }).click()
    await expect(page).toHaveURL("/login")

    // Login via UI form
    await page.getByLabel("Email").fill(email)
    await page.getByLabel("Password").fill(PASSWORD)
    await page.getByRole("button", { name: /sign in/i }).click()

    await expect(page).toHaveURL("/dashboard", { timeout: 10_000 })
  })

  test("logout → login redirect and protected page redirects", async ({ authedPage: page }) => {
    await page.goto("/dashboard")
    await expect(page).toHaveURL("/dashboard")

    await page.getByRole("button", { name: /sign out/i }).click()
    await expect(page).toHaveURL("/login", { timeout: 8_000 })

    // Protected page must redirect to login when unauthenticated
    await page.goto("/dashboard")
    await expect(page).toHaveURL("/login", { timeout: 8_000 })
  })

  test("register with existing email shows error", async ({ page }) => {
    const email = `e2e-dup-${Date.now()}@test.com`

    // Create account via API first
    const res = await page.request.post("/api/v1/auth/register", {
      data: { email, password: PASSWORD },
    })
    expect(res.ok()).toBe(true)

    // Clear cookies so we can access the register page unauthenticated
    await page.context().clearCookies()

    await page.goto("/register")
    await page.getByLabel("Email").fill(email)
    await page.getByLabel("Password").fill(PASSWORD)
    await page.getByLabel("Confirm password").fill(PASSWORD)
    await page.getByRole("button", { name: /create account/i }).click()

    await expect(page).not.toHaveURL("/dashboard")
    await expect(
      page.getByText("Registration failed. Try a different email.")
    ).toBeVisible({ timeout: 8_000 })
  })
})
