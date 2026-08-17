/**
 * Runtime test for unknown enrollment status fallback.
 * Loads admin_dashboard.js in a minimal DOM mock and calls normalizePayload
 * with MANUAL_REVIEW_REQUIRED to verify the fallback path works without
 * ReferenceError on sanitizeHTML.
 */

const fs = require('fs');
const path = require('path');

// Minimal DOM mocks
global.document = {
  addEventListener: () => {},
  createElement: () => ({ getContext: () => null }),
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
};

const vm = require('vm');

// Load and execute the admin_dashboard.js file in the current context
const jsPath = path.join(__dirname, '..', '..', 'static', 'js', 'admin_dashboard.js');
const jsCode = fs.readFileSync(jsPath, 'utf8');

vm.runInThisContext(jsCode, { filename: jsPath });

// Create instance and call normalizePayload
const dashboard = new AdminDashboard();

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

// Verify the unknown status fallback is present
const labels = result.charts.data_submissions.labels;
const values = result.charts.data_submissions.values;

const unknownLabel = labels.find(l => l.includes('MANUAL_REVIEW_REQUIRED') || l.includes('Other status'));
const unknownIndex = labels.indexOf(unknownLabel);

if (!unknownLabel) {
  console.error('FAIL: Unknown status label not found');
  console.error('Labels:', labels);
  process.exit(1);
}

if (values[unknownIndex] !== 3) {
  console.error('FAIL: Unknown status count mismatch');
  console.error('Values:', values);
  process.exit(1);
}

const total = values.reduce((a, b) => a + b, 0);
if (total !== 15) {
  console.error('FAIL: Total count mismatch');
  console.error('Total:', total);
  process.exit(1);
}

console.log('PASS: Unknown enrollment status runtime test passed');
console.log(`  Unknown label: ${unknownLabel}`);
console.log(`  Unknown count: ${values[unknownIndex]}`);
console.log(`  Total: ${total}`);
process.exit(0);
