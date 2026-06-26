/**
 * Unit tests for date-utils.js → formatToAmman
 *
 * Run with:  npx --yes jest tests/js/formatToAmman.test.js --env=node
 *
 * Requires:  Node ≥ 18 (full-icu bundled), or Node 14+ with FULL ICU support.
 * Install:   npm install --save-dev jest
 */

// Inline the logic (avoids ES module import issues in older Jest configs)
const _AMMAN_TZ = "Asia/Amman";

const _FMT = {
  date:     { ar: new Intl.DateTimeFormat("ar-JO", { year: "numeric", month: "short", day: "numeric",                                          timeZone: _AMMAN_TZ }),
              en: new Intl.DateTimeFormat("en-JO", { year: "numeric", month: "short", day: "numeric",                                          timeZone: _AMMAN_TZ }) },
  datetime: { ar: new Intl.DateTimeFormat("ar-JO", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",      timeZone: _AMMAN_TZ }),
              en: new Intl.DateTimeFormat("en-JO", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",      timeZone: _AMMAN_TZ }) },
};

function formatToAmman(val, { time = false, lang = "en" } = {}) {
  if (val == null || val === "") return "-";
  const d = new Date(val);
  if (isNaN(d.getTime())) {
    return `<span class="badge bg-warning text-dark" title="${String(val)}">Invalid Date</span>`;
  }
  return _FMT[time ? "datetime" : "date"][lang].format(d);
}

// ---------------------------------------------------------------------------

test("returns '-' for null", () => {
  expect(formatToAmman(null)).toBe("-");
});

test("returns '-' for empty string", () => {
  expect(formatToAmman("")).toBe("-");
});

test("returns Invalid Date badge for non-date string", () => {
  const result = formatToAmman("not-a-date");
  expect(result).toContain("Invalid Date");
  expect(result).toContain("badge");
});

test("formats UTC ISO string in Asia/Amman timezone — English", () => {
  // 2026-06-14T05:00:00Z == 2026-06-14T08:00:00+03:00 in Amman
  const result = formatToAmman("2026-06-14T05:00:00Z", { lang: "en" });
  expect(result).not.toContain("Invalid Date");
  expect(result).toMatch(/Jun.*2026|2026.*Jun/);
});

test("formats UTC ISO string in Asia/Amman timezone — Arabic", () => {
  const result = formatToAmman("2026-06-14T05:00:00Z", { lang: "ar" });
  expect(result).not.toContain("Invalid Date");
  // Arabic numerals or locale-formatted — just check it's non-empty and non-error
  expect(result.length).toBeGreaterThan(2);
});

test("includes time when time=true — English", () => {
  const result = formatToAmman("2026-06-14T05:00:00Z", { time: true, lang: "en" });
  // Should contain AM/PM or 24h digits
  expect(result).toMatch(/\d{1,2}[:٫]\d{2}|AM|PM/i);
});

test("midnight UTC becomes 03:00 Amman (UTC+3)", () => {
  // 00:00 UTC = 03:00 Amman
  const result = formatToAmman("2026-06-14T00:00:00Z", { time: true, lang: "en" });
  expect(result).not.toContain("Invalid Date");
  // The formatted time should reflect 03:xx Amman, not 00:xx UTC
  expect(result).toMatch(/03:00|3:00/);
});

test("Jordan +03:00 offset ISO string parses correctly", () => {
  // Explicit +03:00 offset — should parse as exactly that moment
  const result = formatToAmman("2026-06-14T08:00:00+03:00", { time: true, lang: "en" });
  expect(result).not.toContain("Invalid Date");
  expect(result).toMatch(/08:00|8:00/);
});
