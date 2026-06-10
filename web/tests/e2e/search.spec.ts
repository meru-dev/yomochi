import { test, expect } from "./fixtures"

const SEARCH_INPUT = 'input[placeholder="Search transactions…"]'

const MOCK_RESULTS = {
  items: [
    {
      id: "s1",
      amount: "1200",
      currency: "JPY",
      date: "2026-01-10",
      type: "expense",
      merchant: "Matcha Bar",
      notes: null,
    },
    {
      id: "s2",
      amount: "800",
      currency: "JPY",
      date: "2026-01-09",
      type: "expense",
      merchant: "Ramen House",
      notes: null,
    },
    {
      id: "s3",
      amount: "500",
      currency: "JPY",
      date: "2026-01-08",
      type: "expense",
      merchant: "Soba Stand",
      notes: null,
    },
  ],
}

test.describe("Inline search — TransactionsView", () => {
  test("≥3 chars — API called, results rendered", async ({ authedPage: page }) => {
    await page.route("**/api/v1/search", (route) =>
      route.fulfill({ json: MOCK_RESULTS }),
    )
    await page.goto("/transactions")

    const requestPromise = page.waitForRequest("**/api/v1/search")
    await page.fill(SEARCH_INPUT, "mat")
    await requestPromise

    await expect(page.getByText("Matcha Bar").first()).toBeVisible()
    await expect(page.getByText("Ramen House").first()).toBeVisible()
  })

  test("<3 chars — API not called, normal list visible", async ({ authedPage: page }) => {
    let searchCalled = false
    await page.route("**/api/v1/search", (route) => {
      searchCalled = true
      return route.fulfill({ json: { items: [] } })
    })
    await page.goto("/transactions")

    await page.fill(SEARCH_INPUT, "ma")
    await page.waitForTimeout(800)

    expect(searchCalled).toBe(false)
    // FilterBar is visible (not in search mode)
    await expect(page.getByRole("button", { name: /expense/i }).first()).toBeVisible()
  })

  test("'searching…' indicator visible while request is pending", async ({ authedPage: page }) => {
    let releaseSearch!: () => void
    const hold = new Promise<void>((resolve) => {
      releaseSearch = resolve
    })

    await page.route("**/api/v1/search", async (route) => {
      await hold
      await route.fulfill({ json: { items: [] } })
    })
    await page.goto("/transactions")

    const requestPromise = page.waitForRequest("**/api/v1/search")
    await page.fill(SEARCH_INPUT, "abc")
    await requestPromise

    // Route is holding — mutation is in pending state
    await expect(page.locator("span", { hasText: "searching…" })).toBeVisible()

    releaseSearch()
  })

  test("clearing search restores filter bar and empty input", async ({ authedPage: page }) => {
    await page.route("**/api/v1/search", (route) =>
      route.fulfill({ json: MOCK_RESULTS }),
    )
    await page.goto("/transactions")

    const requestPromise = page.waitForRequest("**/api/v1/search")
    await page.fill(SEARCH_INPUT, "mat")
    await requestPromise
    await expect(page.getByText("Matcha Bar").first()).toBeVisible()

    // Click the inline "clear" link in the status line
    await page.getByRole("button", { name: "clear" }).click()

    await expect(page.locator(SEARCH_INPUT)).toHaveValue("")
    await expect(page.getByRole("button", { name: /expense/i }).first()).toBeVisible()
  })

  test("empty state when API returns no items", async ({ authedPage: page }) => {
    await page.route("**/api/v1/search", (route) =>
      route.fulfill({ json: { items: [] } }),
    )
    await page.goto("/transactions")

    const requestPromise = page.waitForRequest("**/api/v1/search")
    await page.fill(SEARCH_INPUT, "xyz")
    await requestPromise

    await expect(page.getByText("No results found.")).toBeVisible({ timeout: 5_000 })
  })

  test("result counter shows 'N results'", async ({ authedPage: page }) => {
    await page.route("**/api/v1/search", (route) =>
      route.fulfill({ json: MOCK_RESULTS }),
    )
    await page.goto("/transactions")

    const requestPromise = page.waitForRequest("**/api/v1/search")
    await page.fill(SEARCH_INPUT, "mat")
    await requestPromise

    // Status line: "3 results · clear"
    await expect(page.getByText(/3 results/)).toBeVisible({ timeout: 5_000 })
  })
})
