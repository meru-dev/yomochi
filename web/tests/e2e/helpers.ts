import { expect, type Page } from "@playwright/test"

export async function addTransaction(
  page: Page,
  amount: string,
  merchant: string,
): Promise<void> {
  await page.keyboard.press("n")
  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await page.fill('input[placeholder="0"]', amount)
  await page.fill('input[placeholder="e.g. Starbucks"]', merchant)
  await page.getByRole("button", { name: /save transaction/i }).click()
  await expect(dialog).toBeHidden({ timeout: 10_000 })
}
