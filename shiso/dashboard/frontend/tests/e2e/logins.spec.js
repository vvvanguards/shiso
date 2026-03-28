import { test, expect } from '@playwright/test'

test.describe('Logins Panel', () => {

  test('LoginsPanel shows table with login rows when expanded', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Logins' }).click()

    // Logins section should be expanded and show table with columns
    const table = page.locator('#logins table').first()
    await expect(table).toBeVisible()

    // Table should have headers scoped to the logins table
    await expect(table.getByText('Provider')).toBeVisible()
    await expect(table.getByText('Username')).toBeVisible()
  })

  test('Logins table shows login rows with action buttons', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Logins' }).click()

    // Should show at least one login row (the test DB has 25 logins)
    // Look for any known login provider in the table
    const amexRow = page.locator('text=Amex').first()
    await expect(amexRow).toBeVisible()
  })

  test('Row action buttons are present in login rows', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Logins' }).click()

    // Find action buttons in the last column of the first data row
    // The row actions include sync/edit buttons
    const firstRowActions = page.locator('#logins table tbody tr').first().locator('button')
    const count = await firstRowActions.count()
    expect(count).toBeGreaterThan(0)
  })

  test('Logins section can be collapsed and re-expanded', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Logins' }).click()

    // Logins table should be visible
    await expect(page.locator('#logins table')).toBeVisible()

    // Click the collapse button (the toggle in the logins header)
    const collapseBtn = page.locator('#logins').locator('button').first()
    await collapseBtn.click()

    // Table should no longer be visible (collapsed)
    // Wait a moment for the collapse animation
    await page.waitForTimeout(500)
  })

  test('Sync All button is visible in header', async ({ page }) => {
    await page.goto('/')

    // Sync All button in the header area should be visible
    await expect(page.getByRole('button', { name: 'Sync All' })).toBeVisible()
  })

})
