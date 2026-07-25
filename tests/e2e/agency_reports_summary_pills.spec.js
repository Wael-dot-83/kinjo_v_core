// Regression coverage for the agency-reports dashboard summary pills.
//
// Bug (fixed in ad19204): the pill render loop ran EVERY value through
// Number() + Intl.NumberFormat. The "Last updated" pill's value is a
// formatted date STRING, so Number("25/07/2026, 3:14 AM") -> NaN and the
// pill rendered "ليس رقمًا" (ar) / "NaN" (en) instead of the timestamp.
//
// These tests load the ACTUAL shipping file (no server/auth needed): they
// stub window.fetch, inject the real script, and assert that
//   1. numeric pills are localized + number-formatted, and
//   2. the date/text pill is rendered verbatim and never coerced via Number().
import { test, expect } from '@playwright/test';
import path from 'path';

const SCRIPT_PATH = path.join(
  process.cwd(),
  'static',
  'js',
  'admin_agency_reports_dashboard_summary.js',
);

const SUMMARY = {
  agency_count: 7,
  report_count: 20,
  ready_report_count: 18,
  requires_data_count: 2,
  generated_at: '2026-07-25T00:14:00Z',
};

// Render the real component into a blank page with a stubbed API response.
async function renderPills(page, lang, summary) {
  await page.setContent('<div id="agency-reports-summary"></div>');
  await page.evaluate(
    ({ lang, summary }) => {
      window.KINJO_LANG = lang;
      // Stub fetch BEFORE the IIFE runs so no network/auth is involved.
      window.fetch = () =>
        Promise.resolve({ ok: true, json: () => Promise.resolve(summary) });
    },
    { lang, summary },
  );
  await page.addScriptTag({ path: SCRIPT_PATH });
  await page.waitForSelector('#agency-reports-summary .agency-summary-pill');
  return page.$$eval('#agency-reports-summary .agency-summary-pill', (els) =>
    els.map((e) => ({
      num: e.querySelector('strong')?.textContent ?? '',
      label: e.querySelector('span')?.textContent ?? '',
    })),
  );
}

// Compute the engine's own expected strings so assertions match the exact
// ICU output of the browser running the file (no brittle hardcoded glyphs).
async function expectedStrings(page, locale, summary) {
  return page.evaluate(
    ({ locale, summary }) => ({
      seven: new Intl.NumberFormat(locale).format(7),
      twenty: new Intl.NumberFormat(locale).format(20),
      nan: new Intl.NumberFormat(locale).format(NaN),
      updated: new Date(summary.generated_at).toLocaleString(locale, {
        dateStyle: 'medium',
        timeStyle: 'short',
      }),
    }),
    { locale, summary },
  );
}

test.describe('Agency reports summary pills', () => {
  test('Arabic: numeric pills localized; date pill verbatim, never NaN', async ({
    page,
  }) => {
    const pills = await renderPills(page, 'ar', SUMMARY);
    const exp = await expectedStrings(page, 'ar-JO', SUMMARY);

    expect(pills).toHaveLength(5);

    // Numeric pills: localized + number-formatted (Arabic-Indic digits).
    expect(pills[0].num).toBe(exp.seven);
    expect(pills[1].num).toBe(exp.twenty);
    // Localization actually happened (ar-JO digits differ from ASCII).
    expect(pills[0].num).not.toBe('7');

    // Date pill: rendered verbatim, matching the ICU date-time string.
    const updated = pills.find((p) => p.label.includes('آخر تحديث'));
    expect(updated, 'expected an "آخر تحديث" pill').toBeTruthy();
    expect(updated.num).toBe(exp.updated);

    // Regression guard: must NOT have been coerced through Number().
    expect(updated.num).not.toBe(exp.nan); // "ليس رقمًا"
    expect(updated.num).not.toContain('NaN');
  });

  test('English: numeric pills localized; date pill verbatim, never NaN', async ({
    page,
  }) => {
    const pills = await renderPills(page, 'en', SUMMARY);
    const exp = await expectedStrings(page, 'en-US', SUMMARY);

    expect(pills).toHaveLength(5);

    expect(pills[0].num).toBe(exp.seven); // "7"
    expect(pills[1].num).toBe(exp.twenty); // "20"

    const updated = pills.find((p) => p.label.includes('Last updated'));
    expect(updated, 'expected a "Last updated" pill').toBeTruthy();
    expect(updated.num).toBe(exp.updated);

    // Regression guard: the old bug produced literally "NaN" here.
    expect(updated.num).not.toBe('NaN');
    expect(updated.num).not.toContain('NaN');
  });

  test('missing generated_at falls back to an em dash, not NaN', async ({
    page,
  }) => {
    const summary = { ...SUMMARY, generated_at: null };
    const pills = await renderPills(page, 'en', summary);
    const updated = pills.find((p) => p.label.includes('Last updated'));
    expect(updated.num).toBe('—');
    expect(updated.num).not.toContain('NaN');
  });
});
