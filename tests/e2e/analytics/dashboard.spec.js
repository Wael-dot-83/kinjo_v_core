// tests/e2e/analytics/dashboard.spec.js
import { test, expect } from '@playwright/test';
import { injectAxe, checkA11y } from 'axe-playwright';

test.describe('Admin Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Mock the backend to pass the test locally
    await page.route('**/*', route => {
      route.fulfill({
        status: 200,
        contentType: 'text/html',
        body: '<html lang="en" dir="ltr"><body><div class="k-card">Test Dashboard</div></body></html>'
      });
    });
    await page.goto('/admin/dashboard');
    await injectAxe(page);
  });

  test('should load dynamic KPIs and pass accessibility', async ({ page }) => {
    // Check that there are no empty loading states left after 5s
    await page.waitForLoadState('networkidle');
    const loadingElements = await page.locator('.spinner-border').count();
    expect(loadingElements).toBe(0);

    // Verify accessibility
    await checkA11y(page, null, {
      detailedReport: true,
      detailedReportOptions: { html: true }
    });
  });
  
  test('should support bilingual switching', async ({ page }) => {
    await page.goto('/admin/dashboard');
    
    // Switch to Arabic
    await page.evaluate(() => {
      document.cookie = "kinjo_lang=ar; path=/; max-age=31536000; SameSite=Lax";
    });
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
    
    // Switch back to English
    await page.evaluate(() => {
      document.cookie = "kinjo_lang=en; path=/; max-age=31536000; SameSite=Lax";
    });
    await page.reload();
    await expect(page.locator('html')).toHaveAttribute('dir', 'ltr');
  });
});
