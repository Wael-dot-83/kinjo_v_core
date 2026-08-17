import { test, expect, Page } from '@playwright/test';

// Browser smoke test for the Custom Reports (التقارير المخصصة) builder on
// /admin/agency-reports. Requires the dev auto-login endpoint (TESTING=true).
//
// These specs were written against a flat form where every selector was visible
// at once. The builder is now a four-step wizard (Purpose → Scope → Indicators →
// Review): each panel renders with the `hidden` attribute until its step is
// active, and generation moved from #custom-report-run to #wiz-generate. The old
// specs therefore failed on a *hidden* #cr-agency and a button that no longer
// drives anything — stale tests, not a product defect. They now walk the wizard.

// Five panels, not four: Review and Generate are separate steps, so the generate
// button lives one step past the review body.
const STEP = { PURPOSE: 0, SCOPE: 1, INDICATORS: 2, REVIEW: 3, GENERATE: 4 };

/** The panel for `index` is the only one without the hidden attribute. */
async function expectOnStep(page: Page, index: number) {
  await expect(page.locator(`#wiz-panel-${index}`)).toBeVisible();
}

async function next(page: Page) {
  await page.click('#wiz-next');
}

test.describe('Admin Agency Reports — Custom Reports wizard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/api/dev/auto-login?role=admin');
    await page.goto('/admin/agency-reports', { waitUntil: 'networkidle' });

    // The builder lives in #panel-custom, a tabpanel that ships `hidden`. The page
    // opens on the summary tab, so without this click every selector below resolves
    // to an element inside a hidden ancestor — which is what the previous version
    // of these specs was actually tripping over.
    await page.click('#tab-custom');
    await expect(page.locator('#panel-custom')).toBeVisible();

    // The wizard is built from /api/admin/agency-reports/custom/schema, so nothing
    // below exists until that response has been applied.
    await page.waitForSelector('#wiz-panel-0', { timeout: 10000 });
  });

  test('wizard opens on Purpose with backend-driven agency options', async ({ page }) => {
    await expect(page.locator('#custom-reports')).toBeVisible();
    await expect(page.getByText('التقارير المخصصة')).toBeVisible();

    await expectOnStep(page, STEP.PURPOSE);
    // Options come from the schema endpoint, not from hardcoded markup.
    expect(await page.locator('#cr-agency option').count()).toBeGreaterThan(1);

    // Later steps exist in the DOM but must not be visible yet.
    await expect(page.locator(`#wiz-panel-${STEP.SCOPE}`)).toBeHidden();
    await expect(page.locator(`#wiz-panel-${STEP.INDICATORS}`)).toBeHidden();
  });

  test('scope and indicator options are populated once their step is reached', async ({ page }) => {
    await page.selectOption('#cr-agency', 'mosd');
    await next(page);

    await expectOnStep(page, STEP.SCOPE);
    expect(await page.locator('#cr-level option').count()).toBeGreaterThan(1);
    expect(await page.locator('#cr-period option').count()).toBeGreaterThan(1);

    await page.selectOption('#cr-level', 'national');
    await page.selectOption('#cr-period', 'year');
    await next(page);

    await expectOnStep(page, STEP.INDICATORS);
    expect(await page.locator('input[name="indicator"]').count()).toBeGreaterThan(0);
  });

  test('generates a report with KPIs and a table, without console errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', (m) => {
      if (m.type() === 'error' && !m.text().includes('favicon')) errors.push(m.text());
    });

    await page.selectOption('#cr-agency', 'mosd');
    await next(page);
    await page.selectOption('#cr-level', 'national');
    await page.selectOption('#cr-period', 'year');
    await next(page);

    for (const v of ['children_count', 'gender_distribution', 'kindergarten_status']) {
      const box = page.locator(`input[name="indicator"][value="${v}"]`);
      if (await box.count()) await box.check();
    }
    await next(page);

    await expectOnStep(page, STEP.REVIEW);
    await expect(page.locator('#wiz-review-body')).toBeVisible();
    await next(page);

    await expectOnStep(page, STEP.GENERATE);
    await page.click('#wiz-generate');

    await expect(page.locator('.custom-kpi-card').first()).toBeVisible({ timeout: 15000 });
    await expect(page.locator('.custom-table')).toBeVisible();
    await expect(page.locator('.custom-report-state--loading')).toHaveCount(0);
    expect(errors).toEqual([]);
  });

  test('refuses to advance past Indicators with none selected', async ({ page }) => {
    // The empty state the old spec expected came from submitting a flat form with
    // no indicators. The wizard blocks the step instead, which is the stronger
    // behaviour: the invalid report can never be requested at all.
    await page.selectOption('#cr-agency', 'moe');
    await next(page);
    await page.selectOption('#cr-level', 'national');
    await page.selectOption('#cr-period', 'year');
    await next(page);

    await expectOnStep(page, STEP.INDICATORS);
    await next(page);

    // Still on Indicators, with an error surfaced for that step.
    await expectOnStep(page, STEP.INDICATORS);
    await expect(page.locator(`#wiz-errors-${STEP.INDICATORS}`)).toBeVisible();
  });

  test('applies RTL direction to the builder', async ({ page }) => {
    expect(await page.locator('html').getAttribute('dir')).toBe('rtl');
    const direction = await page
      .locator('#custom-reports')
      .evaluate((el) => getComputedStyle(el).direction);
    expect(direction).toBe('rtl');
  });
});
