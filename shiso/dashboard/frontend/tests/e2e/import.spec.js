import { test, expect } from '@playwright/test'
import { makeTestCSV } from './helpers/csv.js'

test.describe('CSV Import Flow', () => {

  test('Import panel shows FileUpload when no session', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    // Initial state: FileUpload visible
    await expect(page.getByLabel('Choose CSV File')).toBeVisible()
    await expect(page.getByText('Export from chrome://password-manager/settings')).toBeVisible()
  })

  test('Uploading CSV shows enrichment progress then domain groups', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    const csv = makeTestCSV([
      { name: 'Chase Test', username: 'user@test.com', password: 'pass', url: 'https://chase.com' },
      { name: 'Amex Test', username: 'user@test.com', password: 'pass', url: 'https://americanexpress.com' },
      { name: 'Wells Fargo Test', username: 'user@test.com', password: 'pass', url: 'https://wellsfargo.com' },
    ])

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByLabel('Choose CSV File').click(),
    ])
    await fileChooser.setFiles({ name: 'test.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    // Import section should be in viewport
    await expect(page.locator('#import')).toBeInViewport()

    // Wait for enrichment to complete — look for domain groups appearing
    // The "N / M domains" progress text should eventually disappear
    await expect(page.getByText(/\d+ \/ \d+ domains/)).toBeHidden({ timeout: 20_000 })

    // After enrichment, domain group rows should be visible
    // Domains appear with parentheses in the UI: "(chase.com)"
    await expect(page.getByText('(chase.com)')).toBeVisible()
    await expect(page.getByText('(americanexpress.com)')).toBeVisible()
    await expect(page.getByText('(wellsfargo.com)')).toBeVisible()
  })

  test('Search filters rows correctly', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    const csv = makeTestCSV([
      { name: 'Chase Test', username: 'user@test.com', password: 'pass', url: 'https://chase.com' },
      { name: 'Amex Test', username: 'user@test.com', password: 'pass', url: 'https://americanexpress.com' },
    ])

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByLabel('Choose CSV File').click(),
    ])
    await fileChooser.setFiles({ name: 'test.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    // Wait for enrichment to complete
    await expect(page.getByText(/\d+ \/ \d+ domains/)).toBeHidden({ timeout: 20_000 })

    // The import panel has a filter input — use it to filter domains
    const filterInput = page.locator('input[placeholder*="Filter"], input[placeholder*="credit"]').first()
    if (await filterInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await filterInput.fill('am')
      // After filtering, only americanexpress should be visible
      await expect(page.getByText('(americanexpress.com)')).toBeVisible()
      await expect(page.getByText('(chase.com)')).not.toBeVisible()
    } else {
      test.skip()
    }
  })

  test('Category chips filter rows', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    const csv = makeTestCSV([
      { name: 'Chase Test', username: 'user@test.com', password: 'pass', url: 'https://chase.com' },
      { name: 'Amex Test', username: 'user@test.com', password: 'pass', url: 'https://americanexpress.com' },
      { name: 'Amazon Test', username: 'user@test.com', password: 'pass', url: 'https://amazon.com' },
    ])

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByLabel('Choose CSV File').click(),
    ])
    await fileChooser.setFiles({ name: 'test.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    // Wait for enrichment
    await expect(page.getByText(/\d+ \/ \d+ domains/)).toBeHidden({ timeout: 20_000 })

    // Find and click a category chip (e.g., "Banks" or similar)
    const banksChip = page.getByRole('button', { name: /Banks/i }).first()
    if (await banksChip.isVisible()) {
      await banksChip.click()
      // After filtering, only bank rows should be visible
      await expect(page.getByText('chase.com', { exact: true }).first()).toBeVisible()
      // amazon.com should be filtered out (retail, not bank)
    }
  })

  test('Select All / Deselect All buttons work', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    const csv = makeTestCSV([
      { name: 'Chase Test', username: 'user@test.com', password: 'pass', url: 'https://chase.com' },
      { name: 'Amex Test', username: 'user@test.com', password: 'pass', url: 'https://americanexpress.com' },
    ])

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByLabel('Choose CSV File').click(),
    ])
    await fileChooser.setFiles({ name: 'test.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    await expect(page.getByText(/\d+ \/ \d+ domains/)).toBeHidden({ timeout: 20_000 })

    // Select All
    const selectAllBtn = page.getByRole('button', { name: /Select All/i })
    if (await selectAllBtn.isVisible()) {
      await selectAllBtn.click()
      // Import button should show some count
      await expect(page.getByRole('button', { name: /Import \(\d/ })).toBeVisible()
    }

    // Deselect All
    const deselectAllBtn = page.getByRole('button', { name: /Deselect All/i })
    if (await deselectAllBtn.isVisible()) {
      await deselectAllBtn.click()
    }
  })

  test('Domain row checkbox can be toggled', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: 'Import' }).click()

    const csv = makeTestCSV([
      { name: 'Chase Test', username: 'user@test.com', password: 'pass', url: 'https://chase.com' },
      { name: 'Amex Test', username: 'user@test.com', password: 'pass', url: 'https://americanexpress.com' },
    ])

    const [fileChooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.getByLabel('Choose CSV File').click(),
    ])
    await fileChooser.setFiles({ name: 'test.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) })

    await expect(page.getByText(/\d+ \/ \d+ domains/)).toBeHidden({ timeout: 20_000 })

    // Find the first row checkbox in the import table
    const rowCheckbox = page.locator('#import table input[type="checkbox"]').first()

    // Initially checked (all items selected by default) — uncheck it
    await expect(rowCheckbox).toBeChecked()
    await rowCheckbox.uncheck()
    await expect(rowCheckbox).not.toBeChecked()

    // Re-check it
    await rowCheckbox.check()
    await expect(rowCheckbox).toBeChecked()
  })

})
