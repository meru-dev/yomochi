import { test, expect } from "./fixtures"
import { addTransaction } from "./helpers"

const NOW = new Date()
const YEAR = NOW.getFullYear()
const MONTH = NOW.getMonth() + 1
const PERIOD = `${YEAR}-${String(MONTH).padStart(2, "0")}`

const MOCK_INSIGHT = {
  id: "01970000-0000-7000-8000-000000000001",
  status: "COMPLETED",
  period: "MONTHLY",
  period_year: YEAR,
  period_month: MONTH,
  title: "Monthly Spending Overview",
  description: "Your spending was steady across categories.",
  context_quality: "full",
  impact_score: 8,
  generated_at: new Date().toISOString(),
}

test.describe("M6 gate — full user flow", () => {
  test("auth → add 5 transactions → search → request insight → view", async ({ authedPage: page }) => {
    // Mock: category suggest — no AI suggestion
    await page.route("**/api/v1/categories/suggest", (route) =>
      route.fulfill({ json: { category_id: null, name: null, confidence: null } }),
    )

    // Mock: search — return one result matching the first merchant
    await page.route("**/api/v1/search", (route) =>
      route.fulfill({
        json: {
          items: [
            {
              id: "search-tx-1",
              amount: "1000",
              currency: "JPY",
              date: `${PERIOD}-01`,
              type: "expense",
              merchant: "Coffee Shop",
              notes: null,
            },
          ],
        },
      }),
    )

    // Mock: insights — stateful, empty until requested, then COMPLETED
    let insightCreated = false
    await page.route("**/api/v1/insights**", (route, request) => {
      if (request.method() === "POST" && request.url().includes("/requests")) {
        insightCreated = true
        return route.fulfill({ json: MOCK_INSIGHT })
      }
      if (request.method() === "GET") {
        return route.fulfill({
          json: insightCreated
            ? { items: [MOCK_INSIGHT], next_cursor: null }
            : { items: [], next_cursor: null },
        })
      }
      return route.continue()
    })

    // 1. Verify dashboard accessible
    await page.goto("/dashboard")
    await expect(page).toHaveURL("/dashboard")

    // 2. Add 5 transactions
    await page.goto("/transactions")

    const merchants = ["Coffee Shop", "Supermarket", "Gym", "Bookstore", "Restaurant"]
    for (let i = 0; i < merchants.length; i++) {
      await addTransaction(page, String((i + 1) * 1000), merchants[i])
    }

    // 3. Verify timeline
    await expect(page.getByText("Coffee Shop").first()).toBeVisible()
    await expect(page.getByText("Restaurant").first()).toBeVisible()

    // 4. Command palette search
    await page.keyboard.press("Control+k")
    await expect(page.locator('[cmdk-input]')).toBeVisible()
    await page.fill('[cmdk-input]', "coffee")
    await expect(page.getByText("Coffee Shop").first()).toBeVisible()
    await page.keyboard.press("Escape")

    // 5. Navigate to insights
    await page.goto(`/insights/monthly/${PERIOD}`)
    await expect(
      page.getByRole("button", { name: /generate monthly insight/i }),
    ).toBeVisible()

    // 6. Request insight
    await page.getByRole("button", { name: /generate monthly insight/i }).click()

    // 7. Verify completed insight rendered
    await expect(page.getByText("Monthly Spending Overview")).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText("full context")).toBeVisible()
    await expect(page.getByText("Impact score")).toBeVisible()
  })
})
