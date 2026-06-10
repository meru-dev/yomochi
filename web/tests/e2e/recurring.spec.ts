import { test, expect } from "./fixtures"

const MOCK_RULE = {
  id: "01970000-0000-7000-8000-000000000010",
  type: "expense",
  amount: "1000",
  currency: "USD",
  merchant: "Netflix",
  recurrence: "monthly",
  status: "active",
  day_of_month: 1,
  day_of_week: null,
  month: null,
  start_date: "2026-01-01",
  end_date: null,
  next_fire_date: "2026-06-01",
  last_fired_at: null,
}

test.describe("Recurring rules", () => {
  test("create rule → appears in list", async ({ authedPage: page }) => {
    let created = false

    await page.route("**/api/v1/recurring-rules**", (route, request) => {
      if (request.method() === "GET")
        return route.fulfill({ json: { items: created ? [MOCK_RULE] : [], next_cursor: null } })
      if (request.method() === "POST") {
        created = true
        return route.fulfill({ status: 201, json: MOCK_RULE })
      }
      return route.continue()
    })

    await page.goto("/recurring")

    await expect(page.getByText("No recurring rules yet.")).toBeVisible()

    await page.getByRole("button", { name: /\+ add/i }).click()
    await expect(page.getByRole("dialog")).toBeVisible()

    await page.fill('input[placeholder="0"]', "1000")
    await page.fill('input[placeholder="e.g. Netflix"]', "Netflix")
    await page.getByRole("button", { name: /save rule/i }).click()

    await expect(page.getByText("Netflix")).toBeVisible({ timeout: 10_000 })
  })

  test("delete rule → removed from list", async ({ authedPage: page }) => {
    let deleted = false

    await page.route("**/api/v1/recurring-rules**", (route, request) => {
      if (request.method() === "GET")
        return route.fulfill({ json: { items: deleted ? [] : [MOCK_RULE], next_cursor: null } })
      if (request.method() === "DELETE") {
        deleted = true
        return route.fulfill({ status: 204, body: "" })
      }
      return route.continue()
    })

    await page.goto("/recurring")

    await expect(page.getByText("Netflix")).toBeVisible()

    page.once("dialog", (dialog) => dialog.accept())
    await page.getByRole("button", { name: /delete/i }).first().click()

    await expect(page.getByText("Netflix")).not.toBeVisible({ timeout: 8_000 })
    await expect(page.getByText("No recurring rules yet.")).toBeVisible()
  })
})
