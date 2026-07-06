import { test, expect } from "./fixtures"

test.describe("Categories page", () => {
  test("shows system groups and their leaves in hierarchy", async ({ authedPage: page }) => {
    await page.goto("/categories")

    // System groups are present (at least one known group name)
    await expect(page.getByText("Food & Drink")).toBeVisible()

    // At least one leaf is visible (indented under parent)
    await expect(page.getByText("Groceries")).toBeVisible()
  })

  test("creates expense group category", async ({ authedPage: page }) => {
    await page.goto("/categories")

    await page.getByPlaceholder("e.g. Dining").fill("My sport")
    // Type defaults to expense, no parent — creates group
    await page.getByRole("button", { name: /create/i }).click()

    await expect(page.getByText("My sport")).toBeVisible({ timeout: 8000 })
  })

  test("creates leaf under group with matching type", async ({ authedPage: page }) => {
    await page.goto("/categories")

    // Create group first
    await page.getByPlaceholder("e.g. Dining").fill("My hobbies")
    await page.getByRole("button", { name: /create/i }).click()
    await expect(page.getByText("My hobbies")).toBeVisible({ timeout: 8000 })

    // Now create leaf under that group
    const parentSelect = page.locator('[role="combobox"]').first()
    await parentSelect.click()
    await page.getByRole("option", { name: "My hobbies" }).click()

    await page.getByPlaceholder("e.g. Dining").fill("Chess club")
    await page.getByRole("button", { name: /create/i }).click()

    await expect(page.getByText("Chess club")).toBeVisible({ timeout: 8000 })
  })
})

test.describe("Category picker in transaction modal", () => {
  test("expense category picker shows grouped leaves filtered to expense type", async ({ authedPage: page }) => {
    await page.goto("/transactions")

    // Open add-transaction modal
    await page.keyboard.press("n")
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()

    // Type is EXPENSE by default — open category picker
    const categoryTrigger = dialog.locator('[role="combobox"]').last()
    await categoryTrigger.click()

    const dropdown = page.locator('[role="listbox"]')
    await expect(dropdown).toBeVisible()

    // Should show group labels (SelectLabel) — at least one known system group
    await expect(dropdown.getByText("Food & Drink")).toBeVisible()

    // Should show leaf items underneath
    await expect(dropdown.getByRole("option", { name: "Groceries" })).toBeVisible()
  })

  test("switching transaction type to income updates category picker", async ({ authedPage: page }) => {
    await page.goto("/transactions")

    await page.keyboard.press("n")
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()

    // Switch to INCOME
    await dialog.getByRole("button", { name: /income/i }).click()

    const categoryTrigger = dialog.locator('[role="combobox"]').last()
    await categoryTrigger.click()

    const dropdown = page.locator('[role="listbox"]')
    await expect(dropdown).toBeVisible()

    // Income leaves should appear (Salary is a known income leaf)
    await expect(dropdown.getByRole("option", { name: "Salary" })).toBeVisible()
  })
})
