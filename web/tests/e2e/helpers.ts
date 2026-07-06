import { expect, type Page } from "@playwright/test"

export async function addTransaction(
  page: Page,
  amount: string,
  merchant: string,
): Promise<void> {
  await page.keyboard.press("n")
  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  await dialog.getByPlaceholder("0", { exact: true }).fill(amount)
  await dialog.getByPlaceholder("e.g. Starbucks").fill(merchant)
  await page.getByRole("button", { name: /save transaction/i }).click()
  await expect(dialog).toBeHidden({ timeout: 10_000 })
}
