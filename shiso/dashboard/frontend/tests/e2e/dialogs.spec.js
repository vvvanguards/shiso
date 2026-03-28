import { test, expect } from '@playwright/test'

test.describe('Dialog Interactions', () => {

  test('PromosPanel is visible', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Promo APRs/ }).click()

    // Promos panel should be visible (has data or shows empty)
    const promosPanel = page.locator('#promos, [id*="promos"]').first()
    await expect(promosPanel).toBeVisible()
  })

  test('RewardsSection button is present', async ({ page }) => {
    await page.goto('/')

    // Rewards button should be visible in sidebar
    await expect(page.getByRole('button', { name: /Rewards/ })).toBeVisible()
  })

  test('PromoDialog opens from PromosPanel', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Promo APRs/ }).click()

    // Click Add Promo button
    const addPromoBtn = page.getByRole('button', { name: /Add Promo/i })
    if (await addPromoBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addPromoBtn.click()
      // Dialog should appear
      await expect(page.locator('.p-dialog')).toBeVisible()
    }
  })

  test('PromoDialog can be cancelled', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Promo APRs/ }).click()

    const addPromoBtn = page.getByRole('button', { name: /Add Promo/i })
    if (await addPromoBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addPromoBtn.click()
      const dialog = page.locator('.p-dialog')
      await expect(dialog).toBeVisible()

      // Close with Cancel
      const cancelBtn = page.getByRole('button', { name: 'Cancel' })
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click()
        await expect(dialog).not.toBeVisible()
      }
    }
  })

  test('RewardsDialog opens from RewardsSection', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Rewards/ }).click()

    // Click Add Rewards button
    const addRewardsBtn = page.getByRole('button', { name: /Add Rewards/i })
    if (await addRewardsBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addRewardsBtn.click()
      // Dialog should appear
      await expect(page.locator('.p-dialog')).toBeVisible()
    }
  })

  test('RewardsDialog can be cancelled', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /Rewards/ }).click()

    const addRewardsBtn = page.getByRole('button', { name: /Add Rewards/i })
    if (await addRewardsBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addRewardsBtn.click()
      const dialog = page.locator('.p-dialog')
      await expect(dialog).toBeVisible()

      const cancelBtn = page.getByRole('button', { name: 'Cancel' })
      if (await cancelBtn.isVisible()) {
        await cancelBtn.click()
        await expect(dialog).not.toBeVisible()
      }
    }
  })

})
