import { test, expect } from "./fixtures"
import { addTransaction } from "./helpers"

test.describe("Transaction edit and delete", () => {
  test("delete a transaction — removed from list, undo restores it", async ({ authedPage: page }) => {
    await page.goto("/transactions")

    // Add a transaction to delete
    await addTransaction(page, "2500", "Dentist")
    await expect(page.getByText("Dentist").first()).toBeVisible()

    // Hover over the row to reveal actions
    const row = page.locator('[data-testid="tx-row"]').filter({ hasText: "Dentist" }).first()
    await row.hover()

    // Click delete
    const deleteBtn = row.locator('[data-testid="tx-delete"]')
    await expect(deleteBtn).toBeVisible()
    await deleteBtn.click()

    // Row disappears immediately (optimistic)
    await expect(page.locator('[data-testid="tx-row"]').filter({ hasText: "Dentist" })).toBeHidden({ timeout: 3000 })

    // Toast with undo appears
    await expect(page.getByText("✓ Deleted.")).toBeVisible()

    // Click undo — scope to the delete toast, since the earlier "add" toast
    // (also with its own Undo) may still be alive and stacked above it.
    const deleteToast = page.getByText("✓ Deleted.", { exact: true }).locator("xpath=..")
    await deleteToast.getByRole("button", { name: /undo/i }).click()
    await expect(page.getByText("Dentist").first()).toBeVisible({ timeout: 8000 })
  })

  test("edit a transaction — modal pre-fills, save updates list", async ({ authedPage: page }) => {
    await page.goto("/transactions")

    // Add a transaction to edit
    await addTransaction(page, "800", "Bookshop")
    await expect(page.getByText("Bookshop").first()).toBeVisible()

    // Hover over the row to reveal actions
    const row = page.locator('[data-testid="tx-row"]').filter({ hasText: "Bookshop" }).first()
    await row.hover()

    // Click edit
    const editBtn = row.locator('[data-testid="tx-edit"]')
    await expect(editBtn).toBeVisible()
    await editBtn.click()

    // Edit modal opens
    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText("Edit transaction")).toBeVisible()

    // Pre-filled amount is 800
    await expect(dialog.getByPlaceholder("0")).toHaveValue("800")

    // Change merchant name
    const merchantInput = dialog.getByPlaceholder("e.g. Starbucks")
    await merchantInput.clear()
    await merchantInput.fill("Library")

    // Save
    await dialog.getByRole("button", { name: /save changes/i }).click()
    await expect(dialog).toBeHidden({ timeout: 10_000 })

    // Updated merchant appears in list
    await expect(page.getByText("Library").first()).toBeVisible({ timeout: 5000 })
    await expect(page.locator('[data-testid="tx-row"]').filter({ hasText: "Bookshop" })).toBeHidden({ timeout: 5000 })

    // Toast appears
    await expect(page.getByText("✓ Updated.")).toBeVisible()
  })
})
