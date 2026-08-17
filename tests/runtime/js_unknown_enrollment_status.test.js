/**
 * Runtime test for unknown enrollment status fallback.
 * Loads admin_dashboard.js in a minimal DOM mock and calls normalizePayload
 * and renderSubmissionsChart to verify:
 *  - unknown statuses are localized without raw enum suffix,
 *  - multiple unknowns aggregate under a single fallback,
 *  - malicious status strings do not create HTML or execute scripts,
 *  - accessible-table labels contain no raw enum values.
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const createdElements = [];

function createElementMock(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    getContext: () => null,
    setAttribute: () => {},
    classList: { add: () => {} },
    innerHTML: '',
    textContent: '',
    children: [],
    append: () => {},
    querySelector: () => null,
    querySelectorAll: () => [],
    remove: () => {},
  };
  el.appendChild = (child) => { el.children.push(child); };
  createdElements.push(el);
  return el;
}

// Minimal DOM mocks
global.document = {
  addEventListener: () => {},
  createElement: createElementMock,
  getElementById: (id) => {
    if (id === 'enrollment-status-chart') {
      return {
        tagName: 'canvas',
        getContext: () => null,
        setAttribute: () => {},
        classList: { add: () => {} },
        style: { display: '' },
        closest: () => ({ classList: { add: () => {} }, querySelector: () => null, children: [] }),
        id,
      };
    }
    if (id === 'enrollment-chart-interpretation' || id === 'enrollment-chart-accessible-summary') {
      return {
        tagName: 'div',
        innerHTML: '',
        appendChild: () => {},
        id,
      };
    }
    return null;
  },
  querySelector: () => null,
  documentElement: {
    classList: { contains: () => false },
  },
};
global.window = {
  KINJO_LANG: 'en',
  AdminI18n: {
    translate: (key, fallback) => fallback,
  },
  KINJO_ADMIN_FLAGS: {},
  localStorage: {
    getItem: () => null,
  },
  CustomEvent: class CustomEvent {
    constructor(type, options = {}) {
      this.type = type;
      this.detail = options.detail || null;
    }
  },
  dispatchEvent: () => {},
  getComputedStyle: () => ({
    getPropertyValue: () => '',
  }),
};

// Mock safeChartData from chart_utils.js
global.safeChartData = function safeChartData(arr) {
  if (!Array.isArray(arr)) return [];
  return arr.map((v) => (v == null ? 0 : v));
};

// Mock Chart to avoid real canvas dependency
global.Chart = class MockChart {
  constructor() {}
  destroy() {}
};

const jsPath = path.join(__dirname, '..', '..', 'static', 'js', 'admin_dashboard.js');
const jsCode = fs.readFileSync(jsPath, 'utf8');

vm.runInThisContext(jsCode, { filename: jsPath });

const dashboard = new AdminDashboard();

function assert(condition, message) {
  if (!condition) {
    console.error('FAIL:', message);
    process.exit(1);
  }
}

// ── Test 1: single unknown status ───────────────────────────────────────────
{
  const testData = {
    kpis: {},
    summary: {},
    system_overview: {},
    charts: {
      attendance: [],
      enrollment: {
        'ACTIVE': 12,
        'MANUAL_REVIEW_REQUIRED': 3,
      },
      incidents: [],
    },
    alerts: [],
    recent_activity: [],
    kpi_trends: {},
    generated_at: new Date().toISOString(),
  };

  const result = dashboard.normalizePayload(testData);
  const labels = result.charts.data_submissions.labels;
  const values = result.charts.data_submissions.values;

  assert(labels.length === 2, `Expected 2 labels, got ${labels.length}: ${JSON.stringify(labels)}`);
  assert(labels.includes('Active'), `Expected "Active" label, got ${JSON.stringify(labels)}`);
  assert(labels.includes('Other status'), `Expected "Other status" label, got ${JSON.stringify(labels)}`);

  const unknownIndex = labels.indexOf('Other status');
  assert(unknownIndex !== -1, 'Other status label not found');
  assert(values[unknownIndex] === 3, `Expected unknown count 3, got ${values[unknownIndex]}`);

  const activeIndex = labels.indexOf('Active');
  assert(values[activeIndex] === 12, `Expected active count 12, got ${values[activeIndex]}`);

  const total = values.reduce((a, b) => a + b, 0);
  assert(total === 15, `Expected total 15, got ${total}`);

  // No raw enum in visible labels
  assert(!labels.some(l => l.includes('MANUAL_REVIEW_REQUIRED')), 'Raw enum found in visible labels');
}

// ── Test 2: multiple unknown statuses aggregate ─────────────────────────────
{
  const testData = {
    kpis: {},
    summary: {},
    system_overview: {},
    charts: {
      attendance: [],
      enrollment: {
        'ACTIVE': 12,
        'MANUAL_REVIEW_REQUIRED': 3,
        'LEGACY_MIGRATION_STATE': 2,
      },
      incidents: [],
    },
    alerts: [],
    recent_activity: [],
    kpi_trends: {},
    generated_at: new Date().toISOString(),
  };

  const result = dashboard.normalizePayload(testData);
  const labels = result.charts.data_submissions.labels;
  const values = result.charts.data_submissions.values;

  assert(labels.length === 2, `Expected 2 labels after aggregation, got ${labels.length}: ${JSON.stringify(labels)}`);
  assert(labels.includes('Active'), `Expected "Active" label, got ${JSON.stringify(labels)}`);
  assert(labels.includes('Other status'), `Expected "Other status" label, got ${JSON.stringify(labels)}`);

  const unknownIndex = labels.indexOf('Other status');
  assert(values[unknownIndex] === 5, `Expected aggregated unknown count 5, got ${values[unknownIndex]}`);

  const total = values.reduce((a, b) => a + b, 0);
  assert(total === 17, `Expected total 17, got ${total}`);

  assert(!labels.some(l => l.includes('MANUAL_REVIEW_REQUIRED') || l.includes('LEGACY_MIGRATION_STATE')),
    'Raw enum found in visible labels after aggregation');
}

// ── Test 3: malicious status string ─────────────────────────────────────────
{
  const malicious = '<img src=x onerror=alert(1)>';
  const testData = {
    kpis: {},
    summary: {},
    system_overview: {},
    charts: {
      attendance: [],
      enrollment: {
        'ACTIVE': 5,
        [malicious]: 2,
      },
      incidents: [],
    },
    alerts: [],
    recent_activity: [],
    kpi_trends: {},
    generated_at: new Date().toISOString(),
  };

  const result = dashboard.normalizePayload(testData);
  const labels = result.charts.data_submissions.labels;
  const values = result.charts.data_submissions.values;

  assert(labels.length === 2, `Expected 2 labels, got ${labels.length}: ${JSON.stringify(labels)}`);
  assert(labels.includes('Active'), `Expected "Active" label, got ${JSON.stringify(labels)}`);
  assert(labels.includes('Other status'), `Expected "Other status" label, got ${JSON.stringify(labels)}`);

  const unknownIndex = labels.indexOf('Other status');
  assert(values[unknownIndex] === 2, `Expected malicious unknown count 2, got ${values[unknownIndex]}`);

  assert(!labels.some(l => l.includes('<img') || l.includes('onerror') || l.includes('alert')),
    'Malicious HTML found in visible labels');

  const total = values.reduce((a, b) => a + b, 0);
  assert(total === 7, `Expected total 7, got ${total}`);
}

// ── Test 4: renderSubmissionsChart accessible table ─────────────────────────
{
  createdElements.length = 0;
  const testData = {
    kpis: {},
    summary: {},
    system_overview: {},
    charts: {
      attendance: [],
      enrollment: {
        'ACTIVE': 12,
        'MANUAL_REVIEW_REQUIRED': 3,
      },
      incidents: [],
    },
    alerts: [],
    recent_activity: [],
    kpi_trends: {},
    generated_at: new Date().toISOString(),
  };

  const payload = dashboard.normalizePayload(testData);
  dashboard.renderSubmissionsChart(payload.charts.data_submissions);

  // Find the accessible table
  const tableEl = createdElements.find(el => el.tagName === 'TABLE');
  assert(tableEl, 'Accessible table not rendered');

  function extractText(node) {
    if (!node) return '';
    if (node.textContent) return node.textContent;
    if (typeof node === 'string') return node;
    if (Array.isArray(node.children)) {
      return node.children.map(extractText).join(' ');
    }
    return '';
  }

  const tableText = extractText(tableEl);
  assert(!tableText.includes('MANUAL_REVIEW_REQUIRED'), 'Raw enum found in accessible table text');
  assert(tableText.includes('Other status'), 'Accessible table missing "Other status"');
}

// ── Test 5: Arabic fallback ──────────────────────────────────────────────────
{
  const prevLang = global.window.KINJO_LANG;
  global.window.KINJO_LANG = 'ar';

  const testData = {
    kpis: {},
    summary: {},
    system_overview: {},
    charts: {
      attendance: [],
      enrollment: {
        'ACTIVE': 12,
        'MANUAL_REVIEW_REQUIRED': 3,
      },
      incidents: [],
    },
    alerts: [],
    recent_activity: [],
    kpi_trends: {},
    generated_at: new Date().toISOString(),
  };

  const result = dashboard.normalizePayload(testData);
  const labels = result.charts.data_submissions.labels;

  assert(labels.includes('نشط'), `Expected Arabic "نشط" label, got ${JSON.stringify(labels)}`);
  assert(labels.includes('حالة أخرى'), `Expected Arabic "حالة أخرى" label, got ${JSON.stringify(labels)}`);

  const unknownIndex = labels.indexOf('حالة أخرى');
  assert(result.charts.data_submissions.values[unknownIndex] === 3,
    `Expected Arabic unknown count 3, got ${result.charts.data_submissions.values[unknownIndex]}`);

  assert(!labels.some(l => l.includes('MANUAL_REVIEW_REQUIRED')), 'Raw enum found in Arabic visible labels');

  global.window.KINJO_LANG = prevLang;
}

console.log('PASS: All unknown enrollment status runtime tests passed');
process.exit(0);
