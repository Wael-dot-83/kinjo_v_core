import { test, expect } from '@playwright/test';

// Browser smoke test for the Custom Reports (التقارير المخصصة) builder on
// /admin/agency-reports. Requires the dev auto-login endpoint (TESTING=true).
test.describe('Admin Agency Reports — Custom Reports', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/api/dev/auto-login?role=admin');
    await page.goto('/admin/agency-reports', { waitUntil: 'networkidle' });
  });

  test('custom reports section loads with backend-driven selectors', async ({ page }) => {
    await expect(page.locator('#custom-reports')).toBeVisible();
    await expect(page.getByText('التقارير المخصصة')).toBeVisible();
    await page.waitForSelector('#cr-agency', { timeout: 10000 });
    expect(await page.locator('#cr-agency option').count()).toBeGreaterThan(1);
    expect(await page.locator('#cr-level option').count()).toBeGreaterThan(1);
    expect(await page.locator('#cr-period option').count()).toBeGreaterThan(1);
    expect(await page.locator('input[name="indicator"]').count()).toBeGreaterThan(0);
  });

  test('runs a custom report and renders KPIs + table without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (m) => {
      if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(m.text());
    });
    await page.waitForSelector('#cr-agency', { timeout: 10000 });
    await page.selectOption('#cr-agency', 'mosd');
    await page.selectOption('#cr-level', 'national');
    await page.selectOption('#cr-period', 'year');
    for (const v of ['children_count', 'gender_distribution', 'kindergarten_status']) {
      await page.check(`input[name="indicator"][value="${v}"]`);
    }
    await page.click('#custom-report-run');
    await expect(page.locator('.custom-kpi-card').first()).toBeVisible({ timeout: 15000 });
    expect(await page.locator('.custom-kpi-card').count()).toBeGreaterThan(0);
    await expect(page.locator('.custom-table')).toBeVisible();
    await expect(page.locator('.custom-dq')).toBeVisible();
    await expect(page.locator('.custom-export-bar button')).toHaveCount(1); // CSV only (Print removed per spec)
    await expect(page.locator('.custom-report-state--loading')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('applies RTL and shows a professional empty state when no indicators chosen', async ({ page }) => {
    expect(await page.locator('html').getAttribute('dir')).toBe('rtl');
    await page.waitForSelector('#cr-agency', { timeout: 10000 });
    await page.selectOption('#cr-agency', 'moe');
    await page.click('#custom-report-run');
    await expect(page.locator('.custom-report-state--empty')).toBeVisible();
  });
});
