import { test, expect } from '@playwright/test'

test('sidebar navigation and page structure', async ({ page }) => {
  // Collect console errors
  const consoleErrors = []
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text())
    }
  })

  await page.goto('/')

  // 1. Page loads without console errors
  await page.waitForLoadState('networkidle')
  expect(consoleErrors).toHaveLength(0)

  // 2. Sidebar is visible with Overview
  await expect(page.locator('nav')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible()

  // Sidebar section groups
  await expect(page.getByText('Finances')).toBeVisible()
  await expect(page.getByText('Status')).toBeVisible()
  await expect(page.getByText('Accounts', { exact: true })).toBeVisible()

  // Section buttons
  await expect(page.getByRole('button', { name: /Liabilities/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Promo APRs/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Bills/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Assets/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Rewards/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Zero Balance/ })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Logins' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Import' })).toBeVisible()

  // 3. SummaryCards visible in overview
  // The overview section uses SummaryCards component
  const overviewSection = page.locator('#overview')
  await expect(overviewSection).toBeVisible()

  // 4. GlobalSearch present
  await expect(page.getByPlaceholder('Search all accounts...')).toBeVisible()

  // 5. Clicking Import scrolls to #import section
  await page.getByRole('button', { name: 'Import' }).click()
  await expect(page.locator('#import')).toBeInViewport()

  // 6. Clicking Overview scrolls back to #overview
  await page.getByRole('button', { name: 'Overview' }).click()
  await expect(page.locator('#overview')).toBeInViewport()
})
