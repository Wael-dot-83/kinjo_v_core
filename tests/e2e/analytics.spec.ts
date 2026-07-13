import { test, expect, Page } from '@playwright/test';

const REAL_DELTAS = {
  attendance_rate: {
    current_value: 88,
    previous_value: 80,
    delta_absolute: 8,
    delta_percent: 10,
    direction: 'up',
    source: 'real',
  },
  incident_rate: {
    current_value: 1.2,
    previous_value: 1.5,
    delta_absolute: -0.3,
    delta_percent: -20,
    direction: 'down',
    source: 'real',
  },
  total_kindergartens: {
    current_value: 12,
    previous_value: 10,
    delta_absolute: 2,
    delta_percent: 20,
    direction: 'up',
    source: 'real',
  },
};

const UNAVAILABLE_DELTAS = {
  attendance_rate: {
    current_value: 88,
    previous_value: null,
    delta_absolute: null,
    delta_percent: null,
    direction: 'neutral',
    source: 'unavailable',
  },
  incident_rate: {
    current_value: 1.2,
    previous_value: null,
    delta_absolute: null,
    delta_percent: null,
    direction: 'neutral',
    source: 'unavailable',
  },
  total_kindergartens: {
    current_value: 12,
    previous_value: null,
    delta_absolute: null,
    delta_percent: null,
    direction: 'neutral',
    source: 'unavailable',
  },
};

const dashboardData = {
  network_summary: {
    total_kindergartens: 12,
    total_children: 360,
    attendance_rate: 88,
    incident_rate: 1.2,
    enrollment_rate: 92,
    deltas: REAL_DELTAS,
  },
  governorate_breakdown: [
    {
      governorate: 'Amman',
      kindergarten_count: 12,
      children_count: 360,
      attendance_rate: 88,
      incident_rate: 1.2,
      governance_score: 86,
    },
  ],
  attendance_trend: [
    { date: '2026-06-01', value: 84 },
    { date: '2026-06-02', value: 88 },
  ],
  incident_trend: [
    { date: '2026-06-01', value: 1.5 },
    { date: '2026-06-02', value: 1.2 },
  ],
  risk_radar: [
    {
      child_id: 1,
      kindergarten_id: 1,
      child_name: 'Ahmad Ali',
      kindergarten_name: 'Al-Noor',
      risk_type: 'attendance',
      risk_value: 72,
      description: 'Attendance variance',
    },
  ],
  governance_distribution: { green: 1, amber: 0, red: 0 },
};

const predictData = {
  points: [
    { date: '2026-06-01', value: 84 },
    { date: '2026-06-02', value: 88 },
  ],
  forecast_points: [{ date: '2026-07-01', value: 91 }],
  confidence: {
    lower: [{ date: '2026-07-01', value: 86 }],
    upper: [{ date: '2026-07-01', value: 96 }],
  },
  model_meta: {
    last_trained: '2026-06-01',
    model_version: 'v1',
    confidence: 0.9,
  },
};

async function mockAnalyticsRuntime(page: Page, unavailableDeltas = false) {
  const requestedUrls: string[] = [];

  await page.route('**/api/admin/options/governorates', async (route) => {
    await route.fulfill({
      json: {
        governorates: [
          { id: 'all', name_ar: 'الكل', name_en: 'All' },
          { id: 'amman', name_ar: 'عمان', name_en: 'Amman' },
        ],
      },
    });
  });

  // Unified locations API (the governorate filter now reads this): envelope
  // { data: { governorates: [{ key, name_ar, name_en }] } }.
  await page.route('**/api/locations/jordan/governorates', async (route) => {
    await route.fulfill({
      json: {
        data: {
          governorates: [
            { key: 'amman', name_ar: 'عمان', name_en: 'Amman' },
          ],
        },
      },
    });
  });

  await page.route('**/api/admin/options/kindergartens', async (route) => {
    await route.fulfill({ json: { kindergartens: [{ id: 'kg-1', name_ar: 'KG 1', name_en: 'KG 1' }] } });
  });

  // The alerts widget also merges KPI-based alerts from this endpoint (outside
  // the /api/analytics namespace); keep it empty so the alert list renders its
  // deterministic empty-state instead of depending on live seed data.
  await page.route('**/api/kpi/alerts', async (route) => {
    await route.fulfill({ json: { alerts: [] } });
  });

  await page.route('**/api/analytics/**', async (route) => {
    const url = new URL(route.request().url());
    requestedUrls.push(url.pathname + url.search);

    if (url.pathname.endsWith('/dashboard-data')) {
      await route.fulfill({
        json: {
          ...dashboardData,
          network_summary: {
            ...dashboardData.network_summary,
            deltas: unavailableDeltas ? UNAVAILABLE_DELTAS : REAL_DELTAS,
          },
        },
      });
      return;
    }

    if (url.pathname.includes('/predict/')) {
      await route.fulfill({ json: predictData });
      return;
    }

    if (url.pathname.endsWith('/governorate-breakdown')) {
      await route.fulfill({ json: dashboardData.governorate_breakdown });
      return;
    }

    if (url.pathname.includes('/rankings/')) {
      await route.fulfill({ json: { rankings: [] } });
      return;
    }

    if (url.pathname.endsWith('/anomalies')) {
      await route.fulfill({ json: { anomalies: [] } });
      return;
    }

    if (url.pathname.endsWith('/alerts')) {
      await route.fulfill({ json: { alerts: [] } });
      return;
    }

    if (url.pathname.endsWith('/data-quality')) {
      await route.fulfill({ json: { completeness_percent: 99 } });
      return;
    }

    if (url.pathname.endsWith('/targets')) {
      await route.fulfill({ json: { targets: [] } });
      return;
    }

    if (url.pathname.includes('/benchmarks/')) {
      await route.fulfill({ json: { benchmarks: [] } });
      return;
    }

    if (url.pathname.includes('/recommendations/')) {
      await route.fulfill({ json: { recommendations: [] } });
      return;
    }

    await route.fulfill({ json: {} });
  });

  return requestedUrls;
}

test.describe('Admin Analytics production checks', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/api/dev/auto-login?role=admin');
    await page.goto('/admin/analytics', { waitUntil: 'networkidle' });
  });

  test('renders help modal once and removes stale System Health nav', async ({ page }) => {
    await expect(page.locator('#helpExpressModal')).toHaveCount(1);
    await expect(page.locator('[data-bs-target="#helpExpressModal"]')).toContainText(/Help|مساعدة/);
    await expect(page.getByText('System Health')).toHaveCount(0);
    await expect(page.getByText('صحة النظام')).toHaveCount(0);
    await expect(page.locator('a[href="/admin/analytics"]')).toHaveCount(1);
  });

  test('renders real deltas or explicit unavailable state', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    await expect(page.locator('#attendanceTrendIndicator')).toContainText(/vs previous period|عن الفترة السابقة/);
    await expect(page.locator('#incidentTrend')).toContainText(/vs previous period|عن الفترة السابقة/);
    await expect(page.locator('#kpiKgGrowth')).toContainText(/vs previous period|عن الفترة السابقة/);

    await page.unroute('**/api/analytics/**');
    await mockAnalyticsRuntime(page, true);
    await page.reload();

    await expect(page.locator('#attendanceTrendIndicator')).toContainText(/No previous-period data|غير متوفر للفترة السابقة/);
    await expect(page.locator('#incidentTrend')).toContainText(/No previous-period data|غير متوفر للفترة السابقة/);
    await expect(page.locator('#kpiKgGrowth')).toContainText(/No previous-period data|غير متوفر للفترة السابقة/);
  });

  test('normalizes governorate options without object labels', async ({ page }) => {
    page.route('**/api/locations/jordan/governorates', async (route) => {
      await route.fulfill({
        json: {
          data: {
            governorates: [
              { key: 'amman', name_ar: 'عمان', name_en: 'Amman' },
            ],
          },
        },
      });
    });

    await page.reload();
    await expect(page.locator('#governorateFilter option[value="amman"]')).toHaveText(/Amman|عمان/);
    await expect(page.locator('#governorateFilter')).not.toContainText('[object Object]');
  });

  test('loads without forbidden console output and with clean analytics runtime', async ({ page }) => {
    const consoleMessages: string[] = [];
    page.on('console', (message) => {
      if (['error', 'log', 'info', 'debug', 'warn'].includes(message.type())) {
        consoleMessages.push(message.text());
      }
    });

    await mockAnalyticsRuntime(page);
    await page.reload();

    await expect(page.locator('#totalKg')).not.toContainText('skeleton');
    await expect.poll(() => consoleMessages).toEqual([]);

    const js = await page.locator('script[src*="admin_analytics.js"]').getAttribute('src');
    if (js) {
      const runtime = await page.request.get(js);
      const source = await runtime.text();
      expect(source).not.toMatch(/console\.(log|info|debug|warn)/);
      expect(source.toLowerCase()).not.toContain('mock');
      expect(source.toLowerCase()).not.toContain('fake trend');
    }
  });

  test('renders visible KPI cards with numeric values', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    for (const id of ['totalKg', 'totalChildren', 'avgAttendance', 'incidentRate', 'enrollmentRate']) {
      await expect(page.locator(`#${id}`)).toBeVisible();
      await expect(page.locator(`#${id}`)).not.toContainText('skeleton');
      await expect(page.locator(`#${id}`)).not.toHaveText('--');
    }
  });

  test('reloads analytics when the governorate filter changes', async ({ page }) => {
    const requestedUrls = await mockAnalyticsRuntime(page);
    await page.reload();

    await page.locator('#governorateFilter').selectOption('amman');

    await expect
      .poll(() => requestedUrls.some((url) => new URL(url, 'http://localhost').searchParams.get('governorate') === 'amman'))
      .toBe(true);
    await expect(page.locator('#governorateTableBody')).not.toContainText('skeleton');
  });

  test('opens export modal with expected report types', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    await page.locator('[data-bs-target="#exportModal"]').first().click();
    await expect(page.locator('#exportModal')).toBeVisible();
    await expect(page.locator('#exportReportType')).toHaveCount(1);
    // Export offers exactly the report types the backend can stream
    // (analytics_service.py export handler): attendance, incidents,
    // compliance, governorate, full_audit. The first is selected by default.
    await expect(page.locator('#exportReportType option')).toHaveCount(5);
    await expect(page.locator('#exportReportType')).toHaveValue('attendance');
    expect(
      await page.locator('#exportReportType option').evaluateAll((options) =>
        (options as HTMLOptionElement[]).map((option) => option.value),
      ),
    ).toEqual([
      'attendance',
      'incidents',
      'compliance',
      'governorate',
      'full_audit',
    ]);
  });

  test('opens help modal with fallback content (no page-specific guide)', async ({ page }) => {
    await page.getByRole('button', { name: /Help|مساعدة/ }).first().click();

    await expect(page.locator('#helpExpressModal')).toBeVisible();
    // The analytics page intentionally ships no #pageHelpContent guide panel
    // (it was removed so live widgets aren't trapped inside a hidden div — see
    // tests/test_analytics_pinpoint_e2e.py::test_pagehelpcontent_is_absent), so
    // the shared Help modal renders its fallback body and default title.
    await expect(page.locator('#helpModalContent')).toContainText(
      /No specific help information|لا توجد معلومات مساعدة/,
    );
    await expect(page.locator('#helpModalTitle')).toContainText(/Help Guide|دليل المساعدة/);
  });

  test('renders chart canvas once without duplicate Chart.js scripts', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    await expect(page.locator('#trendChart')).toBeVisible();
    expect(await page.locator('#trendChart').evaluate((el) => el instanceof HTMLCanvasElement)).toBeTruthy();
    expect(await page.locator('script[src*="chart.js"]').count()).toBeLessThanOrEqual(1);
  });

  test('keeps live analytics sections visible outside hidden help content', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    await expect(page.locator('.az-analytics-page')).toBeVisible();
    // The dashboard groups live sections into pill tabs. Activate each tab and
    // confirm its sections render (i.e. they are real content, not hidden like
    // the on-demand help modal body).
    const sectionsByTab: Record<string, string[]> = {
      'tab-overview-btn': [
        'totalKg',
        'totalChildren',
        'avgAttendance',
        'incidentRate',
        'enrollmentRate',
        'kpiKgGrowth',
        'attendanceTrendIndicator',
        'incidentTrend',
        'trendChart',
        'riskList',
        'alertList',
        'dataQualityScore',
      ],
      'tab-geographic-btn': ['targetList', 'benchmarkList'],
      'tab-governance-btn': ['governancePieChart', 'recommendationList'],
    };
    for (const [tabBtn, ids] of Object.entries(sectionsByTab)) {
      await page.locator(`#${tabBtn}`).click();
      for (const id of ids) {
        await expect(page.locator(`#${id}`)).toBeVisible();
      }
    }
  });

  test('shows retry control after API failure and reloads after retry', async ({ page }) => {
    await page.unroute('**/api/analytics/**');
    await page.route('**/api/analytics/dashboard-data**', async (route) => route.abort());

    await page.reload();
    await expect(page.locator('#trendChartError button')).toBeVisible({ timeout: 10000 });

    await page.unroute('**/api/analytics/dashboard-data**');
    await mockAnalyticsRuntime(page);
    await page.locator('#trendChartError button').click();

    await expect(page.locator('#trendChartOverlay')).toHaveClass(/d-none/, { timeout: 5000 });
  });

  test('shows retry control after invalid dashboard JSON and keeps page alive', async ({ page }) => {
    await page.unroute('**/api/analytics/**');
    await page.route('**/api/analytics/dashboard-data**', async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: '{invalid json',
      });
    });

    await page.reload();

    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('#trendChartError')).toHaveClass(/show/, { timeout: 10000 });
    await expect(page.locator('#trendChartError button')).toBeVisible();
  });

  test('renders forecast cards', async ({ page }) => {
    await mockAnalyticsRuntime(page);
    await page.reload();

    // Forecast cards live on the AI tab.
    await page.locator('#tab-ai-btn').click();
    for (const id of ['attendanceForecast', 'incidentForecast', 'enrollmentForecast']) {
      await expect(page.locator(`#${id}`)).toBeVisible();
      await expect(page.locator(`#${id}`)).not.toHaveText('--');
    }
  });

  test('applies RTL computed direction', async ({ page }) => {
    expect(await page.locator('html').getAttribute('dir')).toBe('rtl');
    const direction = await page.locator('.az-analytics-page').evaluate((el) => getComputedStyle(el).direction);
    expect(direction).toBe('rtl');
  });
});
