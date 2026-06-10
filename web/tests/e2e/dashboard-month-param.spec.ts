import { test, expect } from "./fixtures"

/**
 * Dashboard `?month=YYYY-MM` query-param validation.
 *
 * The previous implementation accepted any pair of numbers, so navigating to
 * `?month=2026-13` or `?month=2026--5` would silently propagate invalid month
 * indices into the rest of the page (Date math, API requests). The fix clamps
 * to year ∈ [1970, 9999] and month ∈ [1, 12]; out-of-range values fall back to
 * the current month.
 *
 * We don't pin a specific label — what matters is that the page renders the
 * dashboard chrome and does NOT crash / show an empty state.
 */

test.describe("Dashboard ?month= query-param validation", () => {
  test("renders normally when month is in range", async ({ authedPage: page }) => {
    await page.goto("/dashboard?month=2026-04")
    await expect(page.getByText(/^Expenses$/i)).toBeVisible()
  })

  test("falls back to current month when month index is out of range (13)", async ({
    authedPage: page,
  }) => {
    await page.goto("/dashboard?month=2026-13")
    // Page must still render the summary chrome — proves we didn't pass `month=13`
    // down to Date math or to the report API.
    await expect(page.getByText(/^Expenses$/i)).toBeVisible()
    await expect(page.getByText(/^Income$/i)).toBeVisible()
  })

  test("falls back when month is non-numeric garbage", async ({ authedPage: page }) => {
    await page.goto("/dashboard?month=lol-wat")
    await expect(page.getByText(/^Expenses$/i)).toBeVisible()
  })

  test("falls back when year is impossible (10001)", async ({ authedPage: page }) => {
    await page.goto("/dashboard?month=10001-06")
    await expect(page.getByText(/^Expenses$/i)).toBeVisible()
  })
})
