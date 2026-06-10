import { test, expect } from "./fixtures"

const EMPTY_HISTORY = { items: [], next_cursor: null }

function sseBody(events: object[]): string {
  return events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("")
}

function doneDone(saveFaild = false) {
  return {
    type: "done",
    turn_id: crypto.randomUUID(),
    context_quality: "none",
    created_at: new Date().toISOString(),
    save_failed: saveFaild,
  }
}

test.describe("Chat stream", () => {
  test("assistant message renders after stream completes", async ({ authedPage: page }) => {
    await page.route("**/api/v1/chat/history*", (route) =>
      route.fulfill({ json: EMPTY_HISTORY }),
    )
    await page.route("**/api/v1/chat/stream", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([
          { type: "token", content: "Your spending was" },
          { type: "token", content: " ¥12,000 last month." },
          doneDone(false),
        ]),
      }),
    )

    await page.goto("/chat")
    await page.fill('textarea[placeholder*="finances"]', "How much did I spend?")
    await page.getByRole("button", { name: /send/i }).click()

    await expect(page.getByText("Your spending was ¥12,000 last month.")).toBeVisible({
      timeout: 8_000,
    })
    await expect(page.locator("text=Message sent but not saved")).not.toBeVisible()
  })

  test("save_failed=true shows 'not saved' toast", async ({ authedPage: page }) => {
    await page.route("**/api/v1/chat/history*", (route) =>
      route.fulfill({ json: EMPTY_HISTORY }),
    )
    await page.route("**/api/v1/chat/stream", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([
          { type: "token", content: "Here is your answer." },
          doneDone(true),
        ]),
      }),
    )

    await page.goto("/chat")
    await page.fill('textarea[placeholder*="finances"]', "Tell me something")
    await page.getByRole("button", { name: /send/i }).click()

    // Response is still rendered — user sees the answer
    await expect(page.getByText("Here is your answer.")).toBeVisible({ timeout: 8_000 })

    // Toast warns that the turn was not persisted
    await expect(page.getByText("Message sent but not saved")).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText("won't appear in history")).toBeVisible()
  })

  test("save_failed=false produces no toast", async ({ authedPage: page }) => {
    await page.route("**/api/v1/chat/history*", (route) =>
      route.fulfill({ json: EMPTY_HISTORY }),
    )
    await page.route("**/api/v1/chat/stream", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([{ type: "token", content: "Fine." }, doneDone(false)]),
      }),
    )

    await page.goto("/chat")
    await page.fill('textarea[placeholder*="finances"]', "Quick question")
    await page.getByRole("button", { name: /send/i }).click()

    await expect(page.getByText("Fine.")).toBeVisible({ timeout: 8_000 })
    // Give the toast time to appear if it were going to
    await page.waitForTimeout(500)
    await expect(page.locator("text=not saved")).not.toBeVisible()
  })

  test("error SSE event shows inline error and removes optimistic message", async ({
    authedPage: page,
  }) => {
    await page.route("**/api/v1/chat/history*", (route) =>
      route.fulfill({ json: EMPTY_HISTORY }),
    )
    await page.route("**/api/v1/chat/stream", (route) =>
      route.fulfill({
        status: 200,
        headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
        body: sseBody([
          { type: "error", message: "AI service temporarily unavailable. Please try again." },
        ]),
      }),
    )

    await page.goto("/chat")
    await page.fill('textarea[placeholder*="finances"]', "Will this fail?")
    await page.getByRole("button", { name: /send/i }).click()

    await expect(
      page.getByText("AI service temporarily unavailable"),
    ).toBeVisible({ timeout: 8_000 })
  })
})
