/**
 * Unified dashboard client logic for ADMIN, MANAGER, SUPERVISOR, and PARENT.
 * It hydrates widgets defensively: if an element does not exist for a role,
 * the updater simply no-ops.
 */

const DASHBOARD_API = {
  supervisor: {
    dashboard: "/api/supervisor/dashboard",
  },
  manager: {
    classes: "/api/manager/classes",
    accounts: "/api/manager/accounts",
    reports: "/api/daily-reports/submitted",
    supervisors: "/api/users?role=SUPERVISOR&limit=100",
    parents: "/api/users?role=PARENT&limit=200",
    kpis: "/api/kpi/dashboard-data",
  },
  admin: {
    dashboard: "/api/admin/dashboard",
    kindergartens: "/api/kindergartens",
    kpis: "/api/kpi/dashboard-data",
  },
};

function dashboardCurrentLang() {
  if (window.AppI18n && window.AppI18n.currentLang) {
    return window.AppI18n.currentLang;
  }
  return document.documentElement.lang === "en" ? "en" : "ar";
}

function dashboardCurrentLocale() {
  return dashboardCurrentLang() === "en" ? "en-US" : "ar-JO";
}

function dashboardText(key, arText, enText) {
  if (window.AppI18n && typeof window.AppI18n.t === "function") {
    const translated = window.AppI18n.t(key);
    if (translated && translated !== key) {
      return translated;
    }
  }
  return dashboardCurrentLang() === "en" ? enText : arText;
}

const DASHBOARD_LITERAL_EN = {
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…ØªØ§Ø­Ø©": "No data available",
  "Ù…Ø±Ø§Ø³Ù„Ø© Ø§Ù„Ù…Ø´Ø±Ù": "Message supervisor",
  "Ù…Ø±Ø§Ø³Ù„Ø© ÙˆÙ„ÙŠ Ø§Ù„Ø£Ù…Ø±": "Message parent",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ ÙØµÙˆÙ„": "No classes",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª ÙØµÙˆÙ„ Ù„Ø¹Ø±Ø¶Ù‡Ø§": "No class data to display",
  "Ù†Ø³Ø¨Ø© Ø¥Ø´ØºØ§Ù„ Ø§Ù„ÙØµÙ„": "Class occupancy rate",
  "Ù†Ø´Ø·": "Active",
  "ØºÙŠØ± Ù†Ø´Ø·": "Inactive",
  "Ø¹Ø±Ø¶ Ø§Ù„ÙØµÙ„": "View class",
  "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„ÙØµÙˆÙ„": "Unable to load classes",
  "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ù…Ù„Ø®Øµ Ø§Ù„ÙØµÙˆÙ„": "Unable to load class summary",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙ‚Ø§Ø±ÙŠØ± Ù…Ø¹Ù„Ù‚Ø©": "No pending reports",
  "ØªØ§Ø±ÙŠØ® ØºÙŠØ± Ù…Ø­Ø¯Ø¯": "Date not specified",
  "Ø§Ù„ÙŠÙˆÙ…": "Today",
  "Ø£Ù…Ø³": "Yesterday",
  "Ø¨Ø§Ù†ØªØ¸Ø§Ø± Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø©": "Pending review",
  "Ø¹Ø±Ø¶ Ø§Ù„ØªÙ‚Ø±ÙŠØ±": "View report",
  "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„ØªÙ‚Ø§Ø±ÙŠØ±": "Unable to load reports",
  "Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†": "Total supervisors",
  "Ø§Ù„Ù†Ø·Ø§Ù‚ Ø§Ù„Ø¥Ø¯Ø§Ø±ÙŠ Ø§Ù„Ø­Ø§Ù„ÙŠ": "Current management scope",
  "Ø§Ù„Ù…Ø´Ø±ÙÙˆÙ† Ø§Ù„Ù†Ø´Ø·ÙˆÙ†": "Active supervisors",
  "Ù…Ù† Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†": "of total supervisors",
  "Ù…Ø¹Ø¯Ù„ Ù†Ø´Ø§Ø· Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†": "Supervisor activity rate",
  "Ø§Ù„Ù…Ø´Ø±ÙÙˆÙ† ØºÙŠØ± Ø§Ù„Ù†Ø´Ø·ÙŠÙ†": "Inactive supervisors",
  "Ù…Ø¹Ø¯Ù„ Ø¹Ø¯Ù… Ø§Ù„Ù†Ø´Ø§Ø·": "Inactivity rate",
  "ØºÙŠØ± Ù…ØªØ§Ø­ Ø­Ø§Ù„ÙŠØ§Ù‹": "Currently unavailable",
  "Ù†Ø³Ø¨Ø© Ø­Ø¶ÙˆØ±": "attendance rate",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø·Ù„Ø¨Ø§Øª": "No requests",
  "Ø¥Ø¬Ø±Ø§Ø¡ ÙÙˆØ±ÙŠ": "Immediate action",
  "ØªØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©": "Needs follow-up",
  "Ù…Ø³ØªÙ‚Ø±": "Stable",
  "Ø­Ø±Ø¬": "Critical",
  "ØªØ­Øª Ø§Ù„Ù…Ø±Ø§Ù‚Ø¨Ø©": "Under monitoring",
  "Ù…Ù…ØªØ§Ø²": "Excellent",
  "Ø¬ÙŠØ¯": "Good",
  "Ù…ØªÙˆØ³Ø·": "Average",
  "Ù…Ù‡Ø¯Ø¯": "At risk",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø±ÙˆØ¶Ø§Øª": "No kindergartens",
  "Ø³Ø§Ø±ÙŠ": "Valid",
  "Ù‚Ø§Ø±Ø¨ Ø¹Ù„Ù‰ Ø§Ù„Ø§Ù†ØªÙ‡Ø§Ø¡": "Expiring soon",
  "Ù…Ù†ØªÙ‡ÙŠ": "Expired",
  "Ø¹Ø±Ø¶ Ø§Ù„Ø±ÙˆØ¶Ø©": "View kindergarten",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª": "No data",
  "ØªÙ†Ø¨ÙŠÙ‡": "Alert",
  "Ø§Ù†ØªÙ‡Ø§Ø¡ Ø§Ù„ØªØ±Ø®ÙŠØµ": "License expiry",
  "Ø·Ù„Ø¨Ø§Øª ØªØ³Ø¬ÙŠÙ„ Ù…Ø¹Ù„Ù‚Ø©": "Pending enrollments",
  "Ø§Ù†Ø®ÙØ§Ø¶ Ø§Ù„Ø­Ø¶ÙˆØ±": "Low attendance",
  "Ø§Ø±ØªÙØ§Ø¹ Ø§Ù„Ø­ÙˆØ§Ø¯Ø«": "High incidents",
  "Ø·Ù„Ø¨Ø§Øª Ø§Ù„ØªØ³Ø¬ÙŠÙ„": "Enrollment requests",
  "Ø§Ù„Ø³Ù„Ø§Ù…Ø©": "Safety",
  "Ø§Ù„ØªØ±Ø®ÙŠØµ": "License",
  "Ø§Ù„Ø§Ù…ØªØ«Ø§Ù„": "Compliance",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙØ§ØµÙŠÙ„ Ù…ØªØ§Ø­Ø©.": "No details available.",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙ†Ø¨ÙŠÙ‡Ø§Øª Ù†Ø´Ø·Ø©": "No active alerts",
  "ÙØªØ­": "Open",
  "Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø­Ø§Ù„Ø§Øª": "Total cases",
  "Ø§Ù„Ø­Ø¶ÙˆØ±": "Attendance",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ø­Ø¶ÙˆØ± Ø¶Ù…Ù† Ø§Ù„ÙØªØ±Ø© Ø§Ù„Ù…Ø®ØªØ§Ø±Ø©":
    "No attendance data for selected range",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø­Ø§Ù„Ø§Øª ØªØ³Ø¬ÙŠÙ„ Ù…ØªØ§Ø­Ø©": "No enrollment states available",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…Ø¤Ø´Ø±Ø§Øª Ø­Ø§Ù„ÙŠØ§Ù‹": "No KPI data available currently",
  "Ø§Ù„Ø§ØªØ¬Ø§Ù‡": "Trend",
  "Ø¹Ø±Ø¶ Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª": "View actions",
  "Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª": "Actions",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø´Ø±ÙˆØ­Ø§Øª Ù…ØªØ§Ø­Ø© Ù„Ù„Ù…Ø¤Ø´Ø±Ø§Øª.": "No KPI explanations available.",
  "Ù„Ø§ ÙŠÙˆØ¬Ø¯ Ø´Ø±Ø­ Ù…ØªØ§Ø­.": "No explanation available.",
  "Ø®Ø·Ø© Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡": "Action plan",
  "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª Ù…Ù‚ØªØ±Ø­Ø© Ù„Ù‡Ø°Ø§ Ø§Ù„Ù…Ø¤Ø´Ø±.":
    "No suggested actions for this KPI.",
  "Ø¹Ø§Ù„ÙŠØ©": "High",
  "Ù…ØªÙˆØ³Ø·Ø©": "Medium",
  "Ù…Ù†Ø®ÙØ¶Ø©": "Low",
  "Ø¥Ø¬Ø±Ø§Ø¡": "Action",
  "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø±ÙˆØ¶Ø§Øª": "Unable to load kindergarten data",
};

function dashboardLiteral(text) {
  if (dashboardCurrentLang() !== "en") {
    return text;
  }
  return DASHBOARD_LITERAL_EN[text] || text;
}

function dashboardTemplate(html) {
  if (dashboardCurrentLang() !== "en" || !html) {
    return html;
  }
  return Object.entries(DASHBOARD_LITERAL_EN).reduce(
    (acc, [ar, en]) => acc.split(ar).join(en),
    String(html)
  );
}

const KPI_DEFINITIONS = [
  {
    key: "overall_gcei",
    label: () =>
      dashboardText(
        "dashboard.kpi.overall_gcei",
        "Ù…Ø¤Ø´Ø± Ø¬ÙˆØ¯Ø© Ø§Ù„Ø­ÙˆÙƒÙ…Ø© Ø§Ù„ÙƒÙ„ÙŠ",
        "Overall governance quality index"
      ),
    unit: "%",
  },
  {
    key: "attendance_rate",
    label: () =>
      dashboardText("dashboard.kpi.attendance_rate", "Ù†Ø³Ø¨Ø© Ø§Ù„Ø­Ø¶ÙˆØ±", "Attendance rate"),
    unit: "%",
  },
  {
    key: "ratio_compliance",
    label: () =>
      dashboardText(
        "dashboard.kpi.ratio_compliance",
        "Ø§Ù…ØªØ«Ø§Ù„ Ù†Ø³Ø¨Ø© Ø§Ù„Ø¥Ø´Ø±Ø§Ù",
        "Supervisor ratio compliance"
      ),
    unit: "%",
  },
  {
    key: "training_completion_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.training_completion",
        "Ø§ÙƒØªÙ…Ø§Ù„ Ø§Ù„ØªØ¯Ø±ÙŠØ¨",
        "Training completion"
      ),
    unit: "%",
  },
  {
    key: "report_submission_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.report_submission",
        "ØªØ³Ù„ÙŠÙ… Ø§Ù„ØªÙ‚Ø§Ø±ÙŠØ±",
        "Report submission"
      ),
    unit: "%",
  },
  {
    key: "incident_rate",
    label: () =>
      dashboardText("dashboard.kpi.incident_rate", "Ù…Ø¹Ø¯Ù„ Ø§Ù„Ø­ÙˆØ§Ø¯Ø«", "Incident rate"),
    unit: "",
  },
  {
    key: "serious_incident_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.serious_incident_rate",
        "Ù…Ø¹Ø¯Ù„ Ø§Ù„Ø­ÙˆØ§Ø¯Ø« Ø§Ù„Ø¬Ø³ÙŠÙ…Ø©",
        "Serious incident rate"
      ),
    unit: "",
  },
  {
    key: "incident_followup_sla",
    label: () =>
      dashboardText(
        "dashboard.kpi.incident_followup_sla",
        "Ø§Ù„Ø§Ù„ØªØ²Ø§Ù… Ø¨Ù…ØªØ§Ø¨Ø¹Ø© Ø§Ù„Ø­ÙˆØ§Ø¯Ø«",
        "Incident follow-up compliance"
      ),
    unit: "%",
  },
  {
    key: "chronic_absence_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.chronic_absence_rate",
        "Ø§Ù„ØºÙŠØ§Ø¨ Ø§Ù„Ù…Ø²Ù…Ù†",
        "Chronic absence rate"
      ),
    unit: "%",
  },
  {
    key: "capacity_utilization_rate",
    label: () =>
      dashboardText(
        "dashboard.kpi.capacity_utilization_rate",
        "Ø§Ø³ØªØºÙ„Ø§Ù„ Ø§Ù„Ø³Ø¹Ø©",
        "Capacity utilization"
      ),
    unit: "%",
  },
  {
    key: "active_enrollments",
    label: () =>
      dashboardText(
        "dashboard.kpi.active_enrollments",
        "Ø§Ù„ØªØ³Ø¬ÙŠÙ„Ø§Øª Ø§Ù„Ù†Ø´Ø·Ø©",
        "Active enrollments"
      ),
    unit: "",
  },
  {
    key: "new_enrollments",
    label: () =>
      dashboardText(
        "dashboard.kpi.new_enrollments",
        "Ø§Ù„ØªØ³Ø¬ÙŠÙ„Ø§Øª Ø§Ù„Ø¬Ø¯ÙŠØ¯Ø©",
        "New enrollments"
      ),
    unit: "",
  },
];

const BAND_BOOTSTRAP = {
  green: "success",
  amber: "warning",
  red: "danger",
  neutral: "secondary",
};

const BAND_LABEL = {
  green: () => dashboardText("dashboard.band.green", "Ø¬ÙŠØ¯", "Good"),
  amber: () => dashboardText("dashboard.band.amber", "ÙŠØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©", "Needs follow-up"),
  red: () => dashboardText("dashboard.band.red", "Ø­Ø±Ø¬", "Critical"),
  neutral: () => dashboardText("dashboard.band.neutral", "Ù…Ø­Ø§ÙŠØ¯", "Neutral"),
};

const DASHBOARD_STATE = {
  kpis: [],
  attendanceChart: null,
  enrollmentChart: null,
  attendanceSeries: [],
  attendanceChartType: "line",
  latestRequestId: 0,
  isLoading: false,
  validation: {
    status: "unknown",
    summary: dashboardText(
      "dashboard.validation.checking",
      "Ø¬Ø§Ø± Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø³Ù„Ø§Ù…Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª...",
      "Validating data integrity..."
    ),
    checks: [],
    lastUpdated: null,
  },
  managerSummary: {
    classes: 0,
    pendingReports: 0,
    activeSupervisors: 0,
    parents: 0,
  },
};
const DASHBOARD_REQUEST_CACHE_KEY = "kinjo_dashboard_response_cache_v1";
const DASHBOARD_CACHE_TTL_MS = 15000;
const dashboardInFlight = new Map();

function nowMs() {
  return Date.now();
}

function shouldCacheDashboardRequest(url) {
  if (!url || typeof url !== "string") return false;
  return (
    url.startsWith("/api/admin/dashboard") ||
    url.startsWith("/api/supervisor/dashboard") ||
    url.startsWith("/api/manager/") ||
    url.startsWith("/api/kpi/") ||
    url.startsWith("/api/users/me")
  );
}

function readDashboardCacheStore() {
  try {
    const raw = sessionStorage.getItem(DASHBOARD_REQUEST_CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch (_error) {
    return {};
  }
}

function writeDashboardCacheStore(store) {
  try {
    sessionStorage.setItem(DASHBOARD_REQUEST_CACHE_KEY, JSON.stringify(store));
  } catch (_error) {
    // Ignore cache persistence failures.
  }
}

function getDashboardCachedResponse(cacheKey) {
  const store = readDashboardCacheStore();
  const entry = store[cacheKey];
  if (!entry || typeof entry !== "object") return null;
  const expiresAt = Number(entry.expiresAt || 0);
  if (!Number.isFinite(expiresAt) || expiresAt <= nowMs()) {
    delete store[cacheKey];
    writeDashboardCacheStore(store);
    return null;
  }
  return entry.payload ?? null;
}

function setDashboardCachedResponse(cacheKey, payload) {
  const store = readDashboardCacheStore();
  store[cacheKey] = {
    payload,
    expiresAt: nowMs() + DASHBOARD_CACHE_TTL_MS,
  };
  writeDashboardCacheStore(store);
}

const currentUserRole = window.currentUserRole || "PARENT";

function safeRoleValue(role) {
  return String(role || "").toUpperCase();
}

function getDashboardDateRange() {
  const state = window.dashboardDateRange || {};
  const params = {};
  if (state.start) params.period_start = state.start;
  if (state.end) params.period_end = state.end;
  if (state.range) params.range = state.range;
  return params;
}

function buildUrlWithParams(url, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === "") return;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item != null && item !== "") query.append(key, String(item));
      });
      return;
    }
    query.append(key, String(value));
  });
  const qs = query.toString();
  return qs ? `${url}?${qs}` : url;
}

function setDashboardLoadingState(isLoading) {
  DASHBOARD_STATE.isLoading = Boolean(isLoading);
  document.body.setAttribute("aria-busy", isLoading ? "true" : "false");
}

function updateValidationIndicator(status, summary, checks = []) {
  const indicator = document.getElementById("validationStatusIndicator");
  const normalizedStatus = ["valid", "warning", "error", "unknown"].includes(status)
    ? status
    : "unknown";
  const resolvedSummary =
    summary || dashboardText("common.not_available", "ØºÙŠØ± Ù…ØªØ§Ø­", "Not available");

  DASHBOARD_STATE.validation = {
    status: normalizedStatus,
    summary: resolvedSummary,
    checks: Array.isArray(checks) ? checks : [],
    lastUpdated: new Date().toISOString(),
  };

  if (!indicator) return;

  indicator.classList.remove("status-valid", "status-warning", "status-error", "status-unknown");
  indicator.classList.add(`status-${normalizedStatus}`);

  const icon = indicator.querySelector("i");
  if (icon) {
    icon.className =
      normalizedStatus === "valid"
        ? "bi bi-check-circle-fill me-1"
        : normalizedStatus === "warning"
          ? "bi bi-exclamation-triangle-fill me-1"
          : normalizedStatus === "error"
            ? "bi bi-x-circle-fill me-1"
            : "bi bi-question-circle-fill me-1";
  }

  const label = indicator.querySelector("span");
  if (label) label.textContent = resolvedSummary;
}

function renderValidationDetails() {
  const container = document.querySelector("#validationDetailsModal .validation-report");
  if (!container) return;

  const state = DASHBOARD_STATE.validation;
  const checks = Array.isArray(state.checks) ? state.checks : [];
  const statusClass =
    state.status === "valid"
      ? "success"
      : state.status === "warning"
        ? "warning"
        : state.status === "error"
          ? "danger"
          : "secondary";
  const statusLabel =
    state.status === "valid"
      ? dashboardText("dashboard.validation.valid", "Ø³Ù„ÙŠÙ…", "Valid")
      : state.status === "warning"
        ? dashboardText(
            "dashboard.validation.warning",
            "ÙŠØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©",
            "Needs follow-up"
          )
        : state.status === "error"
          ? dashboardText(
              "dashboard.validation.error",
              "ØªØ¹Ø°Ø± Ø§Ù„ØªØ­Ù‚Ù‚",
              "Validation failed"
            )
          : dashboardText("dashboard.validation.unknown", "ØºÙŠØ± Ù…Ø¹Ø±ÙˆÙ", "Unknown");

  const rows = checks.length
    ? checks
        .map((check) => {
          const cStatus = check.ok ? "success" : "danger";
          const cLabel = check.ok
            ? dashboardText("common.success", "Ù†Ø¬Ø­", "Passed")
            : dashboardText("common.failed", "ØªØ¹Ø°Ø±", "Failed");
          return `
            <tr>
              <td>${escapeHtml(check.name || "-")}</td>
              <td><span class="badge bg-${cStatus}">${cLabel}</span></td>
              <td>${escapeHtml(check.message || "-")}</td>
            </tr>
          `;
        })
        .join("")
    : `<tr><td colspan="3" class="text-center text-muted py-3">${dashboardText(
        "dashboard.validation.no_extra_details",
        "Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙØ§ØµÙŠÙ„ Ø¥Ø¶Ø§ÙÙŠØ©",
        "No additional details"
      )}</td></tr>`;

  const lastUpdated = state.lastUpdated
    ? new Date(state.lastUpdated).toLocaleString(dashboardCurrentLocale())
    : dashboardText("common.not_available", "ØºÙŠØ± Ù…ØªØ§Ø­", "Not available");

  container.innerHTML = `
    <div class="alert alert-${statusClass}-subtle border border-${statusClass} mb-3">
      <div class="d-flex justify-content-between align-items-center flex-wrap gap-2">
        <div class="fw-semibold">${escapeHtml(state.summary || dashboardText("common.not_available", "ØºÙŠØ± Ù…ØªØ§Ø­", "Not available"))}</div>
        <span class="badge bg-${statusClass}">${statusLabel}</span>
      </div>
      <div class="small text-muted mt-1">${dashboardText("common.last_updated", "Ø¢Ø®Ø± ØªØ­Ø¯ÙŠØ«", "Last updated")}: ${escapeHtml(lastUpdated)}</div>
    </div>
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead>
          <tr>
            <th>${dashboardText("dashboard.validation.check", "Ø§Ù„ÙØ­Øµ", "Check")}</th>
            <th>${dashboardText("dashboard.validation.result", "Ø§Ù„Ù†ØªÙŠØ¬Ø©", "Result")}</th>
            <th>${dashboardText("dashboard.validation.details", "Ø§Ù„ØªÙØ§ØµÙŠÙ„", "Details")}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function updateElementText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = value;
  }
}

function safeNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatNumber(value) {
  return safeNumber(value).toLocaleString(dashboardCurrentLocale());
}

function formatOneDecimal(value) {
  return safeNumber(value).toFixed(1);
}

function formatMaybeNumber(value) {
  if (value == null || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return formatNumber(n);
}

function formatDateLabel(input) {
  if (!input) return "";
  const d = new Date(input);
  if (Number.isNaN(d.getTime())) return String(input);
  return d.toLocaleDateString(dashboardCurrentLocale(), { month: "short", day: "numeric" });
}

function getNameInitial(name) {
  const normalized = String(name || "").trim();
  if (!normalized) return "-";
  return normalized.charAt(0).toUpperCase();
}

function formatLocalizedDate(input) {
  if (!input) return "-";
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) return String(input);
  return parsed.toLocaleDateString(dashboardCurrentLocale());
}

function getDaysSinceDate(input) {
  if (!input) return null;
  const parsed = new Date(input);
  if (Number.isNaN(parsed.getTime())) return null;
  const today = new Date();
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const targetDate = new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  const msPerDay = 24 * 60 * 60 * 1000;
  const raw = Math.floor((todayDate - targetDate) / msPerDay);
  return Math.max(raw, 0);
}

function reportPriorityMeta(reportDate) {
  const days = getDaysSinceDate(reportDate);
  if (days == null) {
    return {
      levelClass: "level-medium",
      label: dashboardText(
        "dashboard.priority.needs_followup",
        "ØªØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©",
        "Needs follow-up"
      ),
    };
  }
  if (days >= 3) {
    return {
      levelClass: "level-high",
      label:
        dashboardCurrentLang() === "en"
          ? `Overdue by ${formatNumber(days)} day(s)`
          : `${dashboardText("dashboard.priority.overdue_prefix", "Ù…ØªØ£Ø®Ø±", "Overdue")} ${formatNumber(days)} ${dashboardText("dashboard.priority.day", "ÙŠÙˆÙ…", "day(s)")}`,
    };
  }
  if (days >= 1) {
    return {
      levelClass: "level-medium",
      label:
        dashboardCurrentLang() === "en"
          ? `Pending review for ${formatNumber(days)} day(s)`
          : `${dashboardText("dashboard.priority.pending_review_since", "Ø¨Ø§Ù†ØªØ¸Ø§Ø± Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø© Ù…Ù†Ø°", "Pending review for")} ${formatNumber(days)} ${dashboardText("dashboard.priority.day", "ÙŠÙˆÙ…", "day(s)")}`,
    };
  }
  return {
    levelClass: "level-low",
    label: dashboardText(
      "dashboard.priority.new_today",
      "ØªÙ‚Ø±ÙŠØ± Ø¬Ø¯ÙŠØ¯ Ø§Ù„ÙŠÙˆÙ…",
      "New report today"
    ),
  };
}

function utilizationColor(percent) {
  const pct = clampPercent(percent);
  if (pct >= 100) return "danger";
  if (pct >= 85) return "warning";
  return "success";
}

function clampPercent(value) {
  const n = safeNumber(value);
  if (n < 0) return 0;
  if (n > 100) return 100;
  return n;
}

function escapeHtml(text) {
  if (text == null) return "";
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function normalizeBand(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase();
  if (!value) return null;
  if (["green", "excellent", "good", "success"].includes(value)) return "green";
  if (["amber", "yellow", "average", "warning", "caution"].includes(value)) return "amber";
  if (["red", "poor", "critical", "danger"].includes(value)) return "red";
  return "neutral";
}

function normalizeTrend(raw) {
  const value = String(raw || "")
    .trim()
    .toLowerCase();
  if (["up", "increase", "rising"].includes(value)) return "up";
  if (["down", "decrease", "falling"].includes(value)) return "down";
  return "flat";
}

function trendSymbol(trend) {
  if (trend === "up") return dashboardText("dashboard.trend.up", "ØµØ§Ø¹Ø¯", "Up");
  if (trend === "down") return dashboardText("dashboard.trend.down", "Ù‡Ø§Ø¨Ø·", "Down");
  return dashboardText("dashboard.trend.flat", "Ø«Ø§Ø¨Øª", "Flat");
}

function inferBand(metricKey, value) {
  const n = safeNumber(value);
  const lowerIsBetter = new Set(["incident_rate", "serious_incident_rate", "chronic_absence_rate"]);

  if (metricKey === "overall_gcei") {
    if (n >= 80) return "green";
    if (n >= 60) return "amber";
    return "red";
  }

  if (metricKey === "capacity_utilization_rate") {
    if (n >= 70 && n <= 95) return "green";
    if ((n >= 50 && n < 70) || (n > 95 && n <= 110)) return "amber";
    return "red";
  }

  if (lowerIsBetter.has(metricKey)) {
    if (n <= 5) return "green";
    if (n <= 10) return "amber";
    return "red";
  }

  if (metricKey === "active_enrollments" || metricKey === "new_enrollments") {
    return "neutral";
  }

  if (n >= 85) return "green";
  if (n >= 70) return "amber";
  return "red";
}

function statusLabel(status) {
  const s = String(status || "").toUpperCase();
  const labels = {
    ACTIVE: dashboardText("status.active", "Ù†Ø´Ø·", "Active"),
    DRAFT: dashboardText("status.draft", "Ù…Ø³ÙˆØ¯Ø©", "Draft"),
    INACTIVE: dashboardText("status.inactive", "ØºÙŠØ± Ù†Ø´Ø·", "Inactive"),
    ARCHIVED: dashboardText("status.archived", "Ù…Ø¤Ø±Ø´Ù", "Archived"),
    PENDING_REVIEW: dashboardText(
      "status.pending_review",
      "Ø¨Ø§Ù†ØªØ¸Ø§Ø± Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø©",
      "Pending review"
    ),
    SUBMITTED: dashboardText("status.submitted", "Ù…Ù‚Ø¯Ù…", "Submitted"),
    APPROVED: dashboardText("status.approved", "Ù…Ø¹ØªÙ…Ø¯", "Approved"),
    WAITLISTED: dashboardText("status.waitlisted", "Ù‚Ø§Ø¦Ù…Ø© Ø§Ù„Ø§Ù†ØªØ¸Ø§Ø±", "Waitlisted"),
    SENT_TO_PARENT: dashboardText(
      "status.sent_to_parent",
      "Ù…Ø±Ø³Ù„ Ù„ÙˆÙ„ÙŠ Ø§Ù„Ø£Ù…Ø±",
      "Sent to parent"
    ),
    ACCEPTED: dashboardText("status.accepted", "Ù…Ù‚Ø¨ÙˆÙ„", "Accepted"),
    REJECTED: dashboardText("status.rejected", "Ù…Ø±ÙÙˆØ¶", "Rejected"),
    WITHDRAWN: dashboardText("status.withdrawn", "Ù…Ù†Ø³Ø­Ø¨", "Withdrawn"),
  };
  return labels[s] || dashboardText("common.unspecified", "ØºÙŠØ± Ù…Ø­Ø¯Ø¯", "Unspecified");
}

async function dashboardFetch(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const canCache = method === "GET" && shouldCacheDashboardRequest(url);
  const cacheKey = `${method}:${url}`;

  if (canCache) {
    const cached = getDashboardCachedResponse(cacheKey);
    if (cached != null) {
      return cached;
    }
    if (dashboardInFlight.has(cacheKey)) {
      return dashboardInFlight.get(cacheKey);
    }
  }

  const requestPromise = (async () => {
    const headers = {
      "Content-Type": "application/json",
      ...options.headers,
    };

    let response = null;
    if (typeof window.fetchWithAuth === "function") {
      response = await window.fetchWithAuth(url, { ...options, headers });
      if (!response) {
        throw new Error(
          dashboardText("auth.login.required", "يتطلب تسجيل الدخول", "Sign-in is required")
        );
      }
    } else {
      const token = localStorage.getItem("kinjo_token") || sessionStorage.getItem("kinjo_token");
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      response = await fetch(url, { ...options, headers });
    }

    if (!response.ok) {
      let message = "";
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const payload = await response.json().catch(() => ({}));
        message = payload?.detail?.message || payload?.detail || payload?.message || "";
      } else {
        message = await response.text().catch(() => "");
      }
      throw new Error(
        message ||
          response.statusText ||
          dashboardText("common.unexpected_error", "حدث خطأ غير متوقع", "Unexpected error")
      );
    }

    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (canCache) {
      setDashboardCachedResponse(cacheKey, payload);
    }
    return payload;
  })();

  if (!canCache) {
    return requestPromise;
  }

  dashboardInFlight.set(cacheKey, requestPromise);
  try {
    return await requestPromise;
  } finally {
    dashboardInFlight.delete(cacheKey);
  }
}

async function loadDashboard() {
  const requestId = ++DASHBOARD_STATE.latestRequestId;
  setDashboardLoadingState(true);
  updateValidationIndicator(
    "unknown",
    dashboardText(
      "dashboard.validation.checking",
      "Ø¬Ø§Ø± Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† Ø³Ù„Ø§Ù…Ø© Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª...",
      "Validating data integrity..."
    )
  );

  try {
    const currentUser = await dashboardFetch("/api/users/me");
    const actualRole = currentUser.role;

    if (actualRole === "SUPERVISOR" && currentUserRole !== "SUPERVISOR") {
      window.location.href = "/supervisor/dashboard";
      return;
    }
    if (actualRole === "PARENT" && currentUserRole !== "PARENT") {
      window.location.href = "/parent/dashboard";
      return;
    }
    if (
      (actualRole === "ADMIN" || actualRole === "MANAGER") &&
      (currentUserRole === "SUPERVISOR" || currentUserRole === "PARENT")
    ) {
      window.location.href = "/dashboard";
      return;
    }

    if (requestId !== DASHBOARD_STATE.latestRequestId) return;

    if (currentUserRole === "SUPERVISOR") {
      await loadSupervisorDashboard();
      updateValidationIndicator(
        "valid",
        dashboardText(
          "dashboard.validation.supervisor_loaded",
          "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ù„ÙˆØ­Ø© Ø§Ù„Ù…Ø´Ø±Ù Ø¨Ù†Ø¬Ø§Ø­",
          "Supervisor dashboard loaded successfully"
        ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "Ù‡ÙˆÙŠØ© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† ØµÙ„Ø§Ø­ÙŠØ© Ø§Ù„Ø¬Ù„Ø³Ø©.",
              "Session validity verified."
            ),
          },
          {
            name: dashboardText(
              "dashboard.validation.supervisor_data",
              "Ø¨ÙŠØ§Ù†Ø§Øª Ù„ÙˆØ­Ø© Ø§Ù„Ù…Ø´Ø±Ù",
              "Supervisor dashboard data"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.core_loaded",
              "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø£Ø³Ø§Ø³ÙŠØ©.",
              "Core data loaded."
            ),
          },
        ]
      );
      return;
    }
    if (currentUserRole === "MANAGER") {
      await loadManagerDashboard();
      const hasAnyKpi = DASHBOARD_STATE.kpis.length > 0;
      updateValidationIndicator(
        hasAnyKpi ? "valid" : "warning",
        hasAnyKpi
          ? dashboardText(
              "dashboard.validation.manager_loaded",
              "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ù„ÙˆØ­Ø© Ø§Ù„Ù…Ø¯ÙŠØ± Ø¨Ù†Ø¬Ø§Ø­",
              "Manager dashboard loaded successfully"
            )
          : dashboardText(
              "dashboard.validation.kpi_missing",
              "ØªÙ… Ø§Ù„ØªØ­Ù…ÙŠÙ„ Ù…Ø¹ Ù†Ù‚Øµ ÙÙŠ Ù…Ø¤Ø´Ø±Ø§Øª KPI",
              "Loaded with missing KPI indicators"
            ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "Ù‡ÙˆÙŠØ© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† ØµÙ„Ø§Ø­ÙŠØ© Ø§Ù„Ø¬Ù„Ø³Ø©.",
              "Session validity verified."
            ),
          },
          {
            name: dashboardText(
              "dashboard.validation.classes_reports",
              "Ø§Ù„ÙØµÙˆÙ„ ÙˆØ§Ù„ØªÙ‚Ø§Ø±ÙŠØ±",
              "Classes and reports"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.operational_loaded",
              "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ø§Ù„Ø£Ù‚Ø³Ø§Ù… Ø§Ù„ØªØ´ØºÙŠÙ„ÙŠØ©.",
              "Operational sections loaded."
            ),
          },
          {
            name: dashboardText("dashboard.validation.kpi", "Ù…Ø¤Ø´Ø±Ø§Øª Ø§Ù„Ø£Ø¯Ø§Ø¡", "KPIs"),
            ok: hasAnyKpi,
            message: hasAnyKpi
              ? dashboardText(
                  "dashboard.validation.kpi_loaded",
                  "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ù…Ø¤Ø´Ø±Ø§Øª KPI.",
                  "KPI indicators loaded."
                )
              : dashboardText(
                  "dashboard.validation.kpi_failed",
                  "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ù…Ø¤Ø´Ø±Ø§Øª KPI Ø¨Ø§Ù„ÙƒØ§Ù…Ù„.",
                  "Unable to load all KPI indicators."
                ),
          },
        ]
      );
      return;
    }
    if (currentUserRole === "ADMIN") {
      await loadAdminDashboard();
      const hasCriticalKpis = DASHBOARD_STATE.kpis.some((kpi) => kpi.band === "red");
      const hasAnyKpi = DASHBOARD_STATE.kpis.length > 0;
      const status = !hasAnyKpi ? "warning" : hasCriticalKpis ? "warning" : "valid";
      const summary = !hasAnyKpi
        ? dashboardText(
            "dashboard.validation.admin_missing_metrics",
            "ØªÙ… Ø§Ù„ØªØ­Ù…ÙŠÙ„ Ù…Ø¹ Ù†Ù‚Øµ ÙÙŠ Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ù…Ø¤Ø´Ø±Ø§Øª",
            "Loaded with missing indicator data"
          )
        : hasCriticalKpis
          ? dashboardText(
              "dashboard.validation.admin_critical_kpis",
              "ØªÙ… Ø§Ù„ØªØ­Ù…ÙŠÙ„ Ù…Ø¹ ÙˆØ¬ÙˆØ¯ Ù…Ø¤Ø´Ø±Ø§Øª Ø­Ø±Ø¬Ø© ØªØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©",
              "Loaded with critical indicators that need follow-up"
            )
          : dashboardText(
              "dashboard.validation.admin_loaded",
              "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ù„ÙˆØ­Ø© Ø§Ù„Ø¥Ø¯Ø§Ø±Ø© Ø¨Ù†Ø¬Ø§Ø­",
              "Admin dashboard loaded successfully"
            );
      updateValidationIndicator(status, summary, [
        {
          name: dashboardText(
            "dashboard.validation.user_identity",
            "Ù‡ÙˆÙŠØ© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…",
            "User identity"
          ),
          ok: true,
          message: dashboardText(
            "dashboard.validation.session_verified",
            "ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† ØµÙ„Ø§Ø­ÙŠØ© Ø§Ù„Ø¬Ù„Ø³Ø©.",
            "Session validity verified."
          ),
        },
        {
          name: dashboardText(
            "dashboard.validation.admin_data",
            "Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø¥Ø¯Ø§Ø±Ø©",
            "Administration data"
          ),
          ok: true,
          message: dashboardText(
            "dashboard.validation.kg_summary_loaded",
            "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø±ÙˆØ¶Ø§Øª ÙˆØ§Ù„Ù…Ù„Ø®Øµ.",
            "Kindergarten and summary data loaded."
          ),
        },
        {
          name: dashboardText("dashboard.validation.kpi", "Ù…Ø¤Ø´Ø±Ø§Øª Ø§Ù„Ø£Ø¯Ø§Ø¡", "KPIs"),
          ok: hasAnyKpi,
          message: hasAnyKpi
            ? dashboardText(
                "dashboard.validation.kpi_loaded",
                "ØªÙ… ØªØ­Ù…ÙŠÙ„ Ù…Ø¤Ø´Ø±Ø§Øª KPI.",
                "KPI indicators loaded."
              )
            : dashboardText(
                "dashboard.validation.kpi_failed",
                "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ù…Ø¤Ø´Ø±Ø§Øª KPI Ø¨Ø§Ù„ÙƒØ§Ù…Ù„.",
                "Unable to load all KPI indicators."
              ),
        },
      ]);
      return;
    }
    if (currentUserRole === "PARENT") {
      await loadParentDashboard();
      updateValidationIndicator(
        "valid",
        dashboardText(
          "dashboard.validation.parent_ready",
          "Ù„ÙˆØ­Ø© ÙˆÙ„ÙŠ Ø§Ù„Ø£Ù…Ø± Ø¬Ø§Ù‡Ø²Ø©",
          "Parent dashboard is ready"
        ),
        [
          {
            name: dashboardText(
              "dashboard.validation.user_identity",
              "Ù‡ÙˆÙŠØ© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…",
              "User identity"
            ),
            ok: true,
            message: dashboardText(
              "dashboard.validation.session_verified",
              "ØªÙ… Ø§Ù„ØªØ­Ù‚Ù‚ Ù…Ù† ØµÙ„Ø§Ø­ÙŠØ© Ø§Ù„Ø¬Ù„Ø³Ø©.",
              "Session validity verified."
            ),
          },
        ]
      );
    }
  } catch (error) {
    console.error("Error loading dashboard:", error);
    updateValidationIndicator(
      "error",
      dashboardText(
        "dashboard.validation.load_failed",
        "ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„Ø¨ÙŠØ§Ù†Ø§Øª Ø¨Ø§Ù„ÙƒØ§Ù…Ù„",
        "Unable to load all data"
      ),
      [
        {
          name: dashboardText(
            "dashboard.validation.user_session",
            "Ø¬Ù„Ø³Ø© Ø§Ù„Ù…Ø³ØªØ®Ø¯Ù…",
            "User session"
          ),
          ok: false,
          message:
            error.message ||
            dashboardText(
              "dashboard.validation.session_fetch_failed",
              "ØªØ¹Ø°Ø± Ø§Ø³ØªØ±Ø¬Ø§Ø¹ Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø¬Ù„Ø³Ø©.",
              "Unable to retrieve session data."
            ),
        },
      ]
    );
    if (error.message && error.message.includes("Forbidden")) {
      try {
        const user = await dashboardFetch("/api/users/me");
        if (user.role === "SUPERVISOR") window.location.href = "/supervisor/dashboard";
        else if (user.role === "PARENT") window.location.href = "/parent/dashboard";
        else window.location.href = "/dashboard";
      } catch {
        window.location.href = "/login";
      }
    }
  } finally {
    if (requestId === DASHBOARD_STATE.latestRequestId) {
      setDashboardLoadingState(false);
      renderValidationDetails();
    }
  }
}

async function loadSupervisorDashboard() {
  try {
    const data = await dashboardFetch(DASHBOARD_API.supervisor.dashboard);
    updateElementText("totalChildren", formatNumber(data.total_children || 0));
    updateElementText("todayAttendance", formatNumber(data.attendance_summary?.today || 0));
    updateElementText("pendingReports", formatNumber(data.pending_reports || 0));
  } catch (error) {
    console.error("Error loading supervisor dashboard:", error);
  }
}

async function loadManagerDashboard() {
  DASHBOARD_STATE.managerSummary = {
    classes: 0,
    pendingReports: 0,
    activeSupervisors: 0,
    parents: 0,
  };
  renderManagerSummary();

  const jobs = await Promise.allSettled([
    loadClasses(),
    loadSubmittedReports(),
    loadSupervisorStats(),
    loadManagerAccounts(),
    loadKPIs(),
  ]);

  renderManagerSummary();

  const failedJobs = jobs.filter((job) => job.status === "rejected");
  if (failedJobs.length > 0) {
    failedJobs.forEach((job) =>
      console.error("Error loading manager dashboard section:", job.reason)
    );
  }
}

async function loadAdminDashboard() {
  try {
    const rangeParams = getDashboardDateRange();
    const dashboardUrl = buildUrlWithParams(DASHBOARD_API.admin.dashboard, rangeParams);
    const kpiUrl = buildUrlWithParams(DASHBOARD_API.admin.kpis, {
      ...rangeParams,
      locale: dashboardCurrentLang(),
    });

    const [adminResult, kpiResult] = await Promise.allSettled([
      dashboardFetch(dashboardUrl),
      dashboardFetch(kpiUrl),
    ]);

    let adminAlerts = [];

    if (adminResult.status === "fulfilled") {
      const dashboard = adminResult.value || {};
      renderAdminSummaryCards(dashboard.summary || {});
      renderAdminSystemOverview(dashboard.system_overview || {});
      renderAdminKindergartensTable(dashboard.kindergartens || []);
      renderPendingReportsList(dashboard.kindergartens || [], dashboard.summary || {});
      renderAttendanceChart(dashboard.charts?.attendance || []);
      renderEnrollmentChart(dashboard.charts?.enrollment || {});
      adminAlerts = Array.isArray(dashboard.alerts) ? dashboard.alerts : [];
      renderAlerts(adminAlerts);
    } else {
      console.error("Error loading admin dashboard payload:", adminResult.reason);
      await loadKindergartensOverview();
    }

    if (kpiResult.status === "fulfilled") {
      await loadKPIs(kpiResult.value);
      if (adminAlerts.length > 0) {
        updateElementText("alertCount", String(adminAlerts.length));
      }
    } else {
      console.error("Error loading KPI payload:", kpiResult.reason);
      await loadKPIs();
    }
  } catch (error) {
    console.error("Error loading admin dashboard:", error);
    await Promise.all([loadKindergartensOverview(), loadKPIs()]);
  }
}

async function loadParentDashboard() {
  // Parent dashboard is mostly server-rendered.
}

function renderManagerSummary() {
  updateElementText("managerSummaryClasses", formatNumber(DASHBOARD_STATE.managerSummary.classes));
  updateElementText(
    "managerSummaryPendingReports",
    formatNumber(DASHBOARD_STATE.managerSummary.pendingReports)
  );
  updateElementText(
    "managerSummarySupervisors",
    formatNumber(DASHBOARD_STATE.managerSummary.activeSupervisors)
  );
  updateElementText("managerSummaryParents", formatNumber(DASHBOARD_STATE.managerSummary.parents));
}

function renderManagerUsersTable(tableId, users, type) {
  const tableBody = document.getElementById(tableId);
  if (!tableBody) return;

  if (!Array.isArray(users) || users.length === 0) {
    const colspan = type === "supervisor" ? 4 : 5;
    tableBody.innerHTML = dashboardTemplate(
      `<tr><td colspan="${colspan}" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…ØªØ§Ø­Ø©</td></tr>`
    );
    return;
  }

  if (type === "supervisor") {
    tableBody.innerHTML = dashboardTemplate(
      users
        .map((user) => {
          const displayName = user.full_name || user.username || "-";
          const initial = getNameInitial(displayName);
          const createdAt = user.created_at
            ? new Date(user.created_at).toLocaleDateString(dashboardCurrentLocale())
            : "-";
          const userId = user.id != null ? String(user.id) : "";
          const profileLink = userId
            ? `/communication/messages?recipient=${encodeURIComponent(userId)}`
            : "#";
          const actionAttrs = userId
            ? 'class="btn btn-sm btn-outline-primary"'
            : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
          return `
          <tr>
            <td>
              <div class="manager-user">
                <span class="manager-user-badge">${escapeHtml(initial)}</span>
                <div>
                  <div class="fw-semibold">${escapeHtml(displayName)}</div>
                  <div class="small text-muted">${escapeHtml(user.username || "-")}</div>
                </div>
              </div>
            </td>
            <td>${escapeHtml(user.email || "-")}</td>
            <td>${escapeHtml(createdAt)}</td>
            <td>
              <a href="${profileLink}" ${actionAttrs} aria-label="${dashboardLiteral("Ù…Ø±Ø§Ø³Ù„Ø© Ø§Ù„Ù…Ø´Ø±Ù")}">
                <i class="bi bi-envelope"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    users
      .map((user) => {
        const displayName = user.full_name || user.username || "-";
        const initial = getNameInitial(displayName);
        const phone = user.phone_number || user.phone || "-";
        const childrenCount = Number.isFinite(Number(user.children_count))
          ? formatNumber(user.children_count)
          : "-";
        const userId = user.id != null ? String(user.id) : "";
        const profileLink = userId
          ? `/communication/messages?recipient=${encodeURIComponent(userId)}`
          : "#";
        const actionAttrs = userId
          ? 'class="btn btn-sm btn-outline-primary"'
          : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';

        return `
        <tr>
          <td>
            <div class="manager-user">
              <span class="manager-user-badge">${escapeHtml(initial)}</span>
              <span class="fw-semibold">${escapeHtml(displayName)}</span>
            </div>
          </td>
          <td>${escapeHtml(user.username || "-")}</td>
          <td>${escapeHtml(phone)}</td>
          <td>${escapeHtml(childrenCount)}</td>
          <td>
            <a href="${profileLink}" ${actionAttrs} aria-label="${dashboardLiteral("Ù…Ø±Ø§Ø³Ù„Ø© ÙˆÙ„ÙŠ Ø§Ù„Ø£Ù…Ø±")}">
              <i class="bi bi-envelope"></i>
            </a>
          </td>
        </tr>
      `;
      })
      .join("")
  );
}

async function loadManagerAccounts() {
  try {
    const managerAccounts = await dashboardFetch(DASHBOARD_API.manager.accounts);
    const supervisors = Array.isArray(managerAccounts?.supervisors)
      ? managerAccounts.supervisors
      : [];
    const parents = Array.isArray(managerAccounts?.parents) ? managerAccounts.parents : [];

    renderManagerUsersTable("supervisorsTable", supervisors, "supervisor");
    DASHBOARD_STATE.managerSummary.parents = parents.length;
    renderManagerUsersTable("parentsTable", parents, "parent");
    return;
  } catch (error) {
    console.error("Error loading manager accounts endpoint:", error);
  }

  const [supervisorsResult, parentsResult] = await Promise.allSettled([
    dashboardFetch(DASHBOARD_API.manager.supervisors),
    dashboardFetch(DASHBOARD_API.manager.parents),
  ]);

  if (supervisorsResult.status === "fulfilled") {
    const supervisorsRaw =
      supervisorsResult.value?.users ||
      supervisorsResult.value?.items ||
      supervisorsResult.value ||
      [];
    const supervisors = Array.isArray(supervisorsRaw) ? supervisorsRaw : [];
    renderManagerUsersTable("supervisorsTable", supervisors, "supervisor");
  } else {
    console.error("Error loading supervisors table:", supervisorsResult.reason);
    renderManagerUsersTable("supervisorsTable", [], "supervisor");
  }

  if (parentsResult.status === "fulfilled") {
    const parentsRaw =
      parentsResult.value?.users || parentsResult.value?.items || parentsResult.value || [];
    const parents = Array.isArray(parentsRaw) ? parentsRaw : [];
    DASHBOARD_STATE.managerSummary.parents = parents.length;
    renderManagerUsersTable("parentsTable", parents, "parent");
  } else {
    console.error("Error loading parents table:", parentsResult.reason);
    DASHBOARD_STATE.managerSummary.parents = 0;
    renderManagerUsersTable("parentsTable", [], "parent");
  }
}

async function loadClasses() {
  const tableBody = document.getElementById("classesTable");
  const overviewTableBodies = Array.from(document.querySelectorAll("#classOverviewTable"));
  const hasOverviewTables = overviewTableBodies.length > 0;
  if (!tableBody && !hasOverviewTables) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.classes);
    const classes = data.classes || data.items || data || [];

    if (!Array.isArray(classes) || classes.length === 0) {
      if (tableBody) {
        tableBody.innerHTML = dashboardTemplate(
          '<tr><td colspan="7" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ ÙØµÙˆÙ„</td></tr>'
        );
      }
      if (hasOverviewTables) {
        const emptyRow = dashboardTemplate(
          '<tr><td colspan="7" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª ÙØµÙˆÙ„ Ù„Ø¹Ø±Ø¶Ù‡Ø§</td></tr>'
        );
        overviewTableBodies.forEach((body) => {
          body.innerHTML = emptyRow;
        });
      }
      DASHBOARD_STATE.managerSummary.classes = 0;
      return;
    }

    const list = Array.isArray(classes) ? classes : [];
    DASHBOARD_STATE.managerSummary.classes = list.length;

    if (tableBody) {
      tableBody.innerHTML = dashboardTemplate(
        list
          .map((cls) => {
            const classId = cls.id != null ? cls.id : cls.class_id;
            const className = cls.name_ar || cls.name || cls.name_en || "-";
            const supervisorName = cls.supervisor_name || cls.current_supervisor?.name || "-";
            const isActive = cls.is_active == null ? true : Boolean(cls.is_active);
            const enrolled = safeNumber(cls.enrolled_count ?? cls.enrolled);
            const waitlist = safeNumber(cls.waitlist_count ?? cls.waiting_list);
            const capacityTotal = safeNumber(cls.capacity_total ?? cls.capacity);
            const utilizationPct =
              capacityTotal > 0 ? clampPercent((enrolled / capacityTotal) * 100) : 0;
            const utilizationClass = utilizationColor(utilizationPct);
            const classUrl = classId != null ? `/classes/${classId}` : "#";
            const actionAttrs =
              classId != null
                ? 'class="btn btn-sm btn-outline-primary"'
                : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
            return `
          <tr>
            <td>${escapeHtml(className)}</td>
            <td>${escapeHtml(supervisorName)}</td>
            <td>
              <div class="manager-capacity-cell">
                <div class="manager-capacity-meta">
                  <span>${formatNumber(capacityTotal)}</span>
                  <span>${formatOneDecimal(utilizationPct)}%</span>
                </div>
                <div class="progress mt-1" role="progressbar" aria-label="${dashboardLiteral("Ù†Ø³Ø¨Ø© Ø¥Ø´ØºØ§Ù„ Ø§Ù„ÙØµÙ„")}"
                  aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(utilizationPct)}">
                  <div class="progress-bar bg-${utilizationClass}" style="width:${utilizationPct}%"></div>
                </div>
              </div>
            </td>
            <td>${formatNumber(enrolled)}</td>
            <td>${formatNumber(waitlist)}</td>
            <td><span class="badge bg-${isActive ? "success" : "secondary"}">${isActive ? dashboardLiteral("Ù†Ø´Ø·") : dashboardLiteral("ØºÙŠØ± Ù†Ø´Ø·")}</span></td>
            <td>
              <a href="${classUrl}" ${actionAttrs} aria-label="${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„ÙØµÙ„")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
          })
          .join("")
      );
    }

    if (hasOverviewTables) {
      const overviewHtml = dashboardTemplate(
        list
          .map((cls) => {
            const classId = cls.id != null ? cls.id : cls.class_id;
            const className = cls.name_ar || cls.name || cls.name_en || "-";
            const isActive = cls.is_active == null ? true : Boolean(cls.is_active);
            const capacity = cls.capacity_total ?? cls.capacity;
            const present = cls.attendance_today ?? cls.present_count ?? null;
            const absent = cls.absent_today ?? cls.absent_count ?? null;
            const pendingReports = cls.pending_reports ?? cls.pending_reports_count ?? null;
            const classUrl = classId != null ? `/classes/${classId}` : "#";
            const actionAttrs =
              classId != null
                ? 'class="btn btn-sm btn-outline-primary"'
                : 'class="btn btn-sm btn-outline-secondary disabled" tabindex="-1" aria-disabled="true"';
            return `
            <tr>
              <td>${escapeHtml(className)}</td>
              <td>${formatMaybeNumber(capacity)}</td>
              <td>${formatMaybeNumber(present)}</td>
              <td>${formatMaybeNumber(absent)}</td>
              <td>${formatMaybeNumber(pendingReports)}</td>
              <td><span class="badge bg-${isActive ? "success" : "secondary"}">${isActive ? dashboardLiteral("Ù†Ø´Ø·") : dashboardLiteral("ØºÙŠØ± Ù†Ø´Ø·")}</span></td>
              <td>
                <a href="${classUrl}" ${actionAttrs} aria-label="${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„ÙØµÙ„")}">
                  <i class="bi bi-eye"></i>
                </a>
              </td>
            </tr>
          `;
          })
          .join("")
      );
      overviewTableBodies.forEach((body) => {
        body.innerHTML = overviewHtml;
      });
    }
  } catch (error) {
    console.error("Error loading classes:", error);
    if (tableBody) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="7" class="text-center py-4 text-danger">ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„ÙØµÙˆÙ„</td></tr>'
      );
    }
    if (hasOverviewTables) {
      const errorRow = dashboardTemplate(
        '<tr><td colspan="7" class="text-center py-4 text-danger">ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ù…Ù„Ø®Øµ Ø§Ù„ÙØµÙˆÙ„</td></tr>'
      );
      overviewTableBodies.forEach((body) => {
        body.innerHTML = errorRow;
      });
    }
    DASHBOARD_STATE.managerSummary.classes = 0;
  }
}

async function loadSubmittedReports() {
  const tableBody = document.getElementById("reportsTable");
  if (!tableBody) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.reports);
    const reports = data.reports || data.items || data || [];
    const reportList = Array.isArray(reports) ? reports : [];
    DASHBOARD_STATE.managerSummary.pendingReports = reportList.length;

    if (reportList.length === 0) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="5" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙ‚Ø§Ø±ÙŠØ± Ù…Ø¹Ù„Ù‚Ø©</td></tr>'
      );
      return;
    }

    tableBody.innerHTML = dashboardTemplate(
      reportList
        .slice(0, 10)
        .map((report) => {
          const dateText = formatLocalizedDate(report.date);
          const submitterName = report.supervisor_name || report.submitted_by || "-";
          const daysSince = getDaysSinceDate(report.date);
          const relativeText =
            daysSince == null
              ? dashboardLiteral("ØªØ§Ø±ÙŠØ® ØºÙŠØ± Ù…Ø­Ø¯Ø¯")
              : daysSince === 0
                ? dashboardLiteral("Ø§Ù„ÙŠÙˆÙ…")
                : daysSince === 1
                  ? dashboardLiteral("Ø£Ù…Ø³")
                  : dashboardCurrentLang() === "en"
                    ? `${formatNumber(daysSince)} day(s) ago`
                    : `${dashboardText("dashboard.time.ago_prefix", "Ù…Ù†Ø°", "ago")} ${formatNumber(daysSince)} ${dashboardText("dashboard.priority.day", "ÙŠÙˆÙ…", "day(s)")}`;
          const priority = reportPriorityMeta(report.date);
          return `
          <tr>
            <td>${escapeHtml(report.child_name || "-")}</td>
            <td>
              <div>${escapeHtml(dateText)}</div>
              <div class="small text-muted">${escapeHtml(relativeText)}</div>
            </td>
            <td>${escapeHtml(submitterName)}</td>
            <td>
              <span class="badge bg-warning">${dashboardLiteral("Ø¨Ø§Ù†ØªØ¸Ø§Ø± Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø©")}</span>
              <div class="manager-report-priority ${priority.levelClass}">
                <i class="bi bi-clock-history"></i>
                <span>${escapeHtml(priority.label)}</span>
              </div>
            </td>
            <td>
              <a href="/reports/${report.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„ØªÙ‚Ø±ÙŠØ±")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
  } catch (error) {
    console.error("Error loading reports:", error);
    DASHBOARD_STATE.managerSummary.pendingReports = 0;
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="5" class="text-center py-4 text-danger">ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø§Ù„ØªÙ‚Ø§Ø±ÙŠØ±</td></tr>'
    );
  }
}

async function loadSupervisorStats() {
  const container = document.getElementById("supervisorStatsContainer");
  if (!container) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.manager.supervisors);
    const supervisors = data.users || data.items || data || [];
    const all = Array.isArray(supervisors) ? supervisors : [];
    const active = all.filter((s) => safeRoleValue(s.status) === "ACTIVE").length;
    const inactive = Math.max(all.length - active, 0);
    const activeRate = all.length > 0 ? (active / all.length) * 100 : 0;
    const inactiveRate = Math.max(100 - activeRate, 0);

    container.innerHTML = dashboardTemplate(`
      <div class="row g-3 manager-stats-grid">
        <div class="col-md-4">
          <div class="card border-0 bg-primary-subtle h-100">
            <div class="card-body">
              <div class="small text-primary mb-1">Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†</div>
              <h3 class="fw-bold mb-0">${formatNumber(all.length)}</h3>
              <div class="small text-muted mt-2">Ø§Ù„Ù†Ø·Ø§Ù‚ Ø§Ù„Ø¥Ø¯Ø§Ø±ÙŠ Ø§Ù„Ø­Ø§Ù„ÙŠ</div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 bg-success-subtle h-100">
            <div class="card-body">
              <div class="small text-success mb-1">Ø§Ù„Ù…Ø´Ø±ÙÙˆÙ† Ø§Ù„Ù†Ø´Ø·ÙˆÙ†</div>
              <h3 class="fw-bold mb-0">${formatNumber(active)}</h3>
              <div class="small text-muted mt-1">${formatOneDecimal(activeRate)}% Ù…Ù† Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†</div>
              <div class="progress manager-stats-progress mt-2" role="progressbar" aria-label="Ù…Ø¹Ø¯Ù„ Ù†Ø´Ø§Ø· Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†"
                aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(activeRate)}">
                <div class="progress-bar bg-success" style="width:${clampPercent(activeRate)}%"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-md-4">
          <div class="card border-0 bg-secondary-subtle h-100">
            <div class="card-body">
              <div class="small text-secondary mb-1">Ø§Ù„Ù…Ø´Ø±ÙÙˆÙ† ØºÙŠØ± Ø§Ù„Ù†Ø´Ø·ÙŠÙ†</div>
              <h3 class="fw-bold mb-0">${formatNumber(inactive)}</h3>
              <div class="small text-muted mt-1">${formatOneDecimal(inactiveRate)}% Ù…Ù† Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ù…Ø´Ø±ÙÙŠÙ†</div>
              <div class="progress manager-stats-progress mt-2" role="progressbar" aria-label="Ù…Ø¹Ø¯Ù„ Ø¹Ø¯Ù… Ø§Ù„Ù†Ø´Ø§Ø·"
                aria-valuemin="0" aria-valuemax="100" aria-valuenow="${formatOneDecimal(inactiveRate)}">
                <div class="progress-bar bg-secondary" style="width:${clampPercent(inactiveRate)}%"></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    `);
    DASHBOARD_STATE.managerSummary.activeSupervisors = active;
  } catch (error) {
    console.error("Error loading supervisor stats:", error);
    DASHBOARD_STATE.managerSummary.activeSupervisors = 0;
    container.innerHTML = dashboardTemplate(
      '<p class="text-muted mb-0">ØºÙŠØ± Ù…ØªØ§Ø­ Ø­Ø§Ù„ÙŠØ§Ù‹</p>'
    );
  }
}

function renderAdminSummaryCards(summary) {
  const attendanceToday = safeNumber(summary.attendance_today);
  const pendingApplications = safeNumber(summary.pending_applications);
  const pendingReports = safeNumber(summary.pending_daily_reports);
  const recentIncidents = safeNumber(summary.recent_incidents);
  const attendanceRate = safeNumber(summary.attendance_rate);

  updateElementText("presentTodayValue", formatNumber(attendanceToday));
  updateElementText("pendingEnrollmentsValue", formatNumber(pendingApplications));
  updateElementText("pendingReportsValue", formatNumber(pendingReports));
  updateElementText("incidentsTodayValue", formatNumber(recentIncidents));

  const progress = document.querySelector("#attendanceCard .progress-bar");
  if (progress) {
    const pct = clampPercent(attendanceRate);
    progress.style.width = `${pct}%`;
    progress.setAttribute("aria-valuenow", String(pct));
  }

  const attendanceNote = document.querySelector("#attendanceCard small.text-muted.mt-1");
  if (attendanceNote) {
    attendanceNote.textContent =
      dashboardCurrentLang() === "en"
        ? `${formatOneDecimal(attendanceRate)}% attendance rate`
        : `${formatOneDecimal(attendanceRate)}% ${dashboardText("dashboard.attendance_rate_suffix", "Ù†Ø³Ø¨Ø© Ø­Ø¶ÙˆØ±", "attendance rate")}`;
  }

  const pendingBadge = document.getElementById("pendingEnrollmentsBadge");
  if (pendingBadge) {
    if (pendingApplications === 0) {
      pendingBadge.className = "badge bg-success-subtle text-success rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ Ø·Ù„Ø¨Ø§Øª");
    } else if (pendingApplications > 10) {
      pendingBadge.className = "badge bg-danger-subtle text-danger rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("Ø¥Ø¬Ø±Ø§Ø¡ ÙÙˆØ±ÙŠ");
    } else {
      pendingBadge.className = "badge bg-warning-subtle text-warning rounded-pill px-3";
      pendingBadge.textContent = dashboardLiteral("ØªØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©");
    }
  }

  const incidentsBadge = document.getElementById("incidentsBadge");
  if (incidentsBadge) {
    if (recentIncidents === 0) {
      incidentsBadge.className = "badge bg-success-subtle text-success rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("Ù…Ø³ØªÙ‚Ø±");
    } else if (recentIncidents >= 5) {
      incidentsBadge.className = "badge bg-danger-subtle text-danger rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("Ø­Ø±Ø¬");
    } else {
      incidentsBadge.className = "badge bg-warning-subtle text-warning rounded-pill px-3";
      incidentsBadge.textContent = dashboardLiteral("ØªØ­Øª Ø§Ù„Ù…Ø±Ø§Ù‚Ø¨Ø©");
    }
  }
}

function renderAdminSystemOverview(overview) {
  const totalKindergartens = safeNumber(overview.total_kindergartens);
  const activeKindergartens = safeNumber(overview.active_kindergartens);
  const totalUsers = safeNumber(overview.total_users);

  updateElementText("totalKindergartens", formatNumber(totalKindergartens));
  updateElementText("activeKindergartens", formatNumber(activeKindergartens));
  updateElementText("totalUsers", formatNumber(totalUsers));

  const health = document.getElementById("systemHealth");
  if (health) {
    const activeRate =
      totalKindergartens > 0 ? (activeKindergartens / totalKindergartens) * 100 : 0;
    if (activeRate >= 90) health.textContent = dashboardLiteral("Ù…Ù…ØªØ§Ø²");
    else if (activeRate >= 75) health.textContent = dashboardLiteral("Ø¬ÙŠØ¯");
    else if (activeRate >= 50) health.textContent = dashboardLiteral("Ù…ØªÙˆØ³Ø·");
    else health.textContent = dashboardLiteral("Ù…Ù‡Ø¯Ø¯");
  }
}

function renderAdminKindergartensTable(kindergartens) {
  const tableBody = document.getElementById("kindergartensOverviewTable");
  if (!tableBody) return;

  if (!Array.isArray(kindergartens) || kindergartens.length === 0) {
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="8" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø±ÙˆØ¶Ø§Øª</td></tr>'
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    kindergartens
      .map((kg) => {
        const statusClass =
          String(kg.status || "").toUpperCase() === "ACTIVE" ? "success" : "secondary";
        const license = String(kg.license_status || "unknown").toLowerCase();
        const licenseClass =
          license === "valid" ? "success" : license === "expiring_soon" ? "warning" : "danger";
        const licenseText =
          license === "valid"
            ? dashboardLiteral("Ø³Ø§Ø±ÙŠ")
            : license === "expiring_soon"
              ? dashboardLiteral("Ù‚Ø§Ø±Ø¨ Ø¹Ù„Ù‰ Ø§Ù„Ø§Ù†ØªÙ‡Ø§Ø¡")
              : dashboardLiteral("Ù…Ù†ØªÙ‡ÙŠ");

        return `
        <tr>
          <td>${escapeHtml(kg.name_ar || kg.name_en || "-")}</td>
          <td><span class="badge bg-${statusClass}">${statusLabel(kg.status)}</span></td>
          <td>${formatNumber(kg.enrollments || 0)}</td>
          <td>${formatNumber(kg.attendance_today || 0)}</td>
          <td>${formatNumber(kg.pending_reports || 0)}</td>
          <td>${formatOneDecimal(kg.capacity_utilization || 0)}%</td>
          <td><span class="badge bg-${licenseClass}">${licenseText}</span></td>
          <td>
            <a href="/kindergartens/${kg.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„Ø±ÙˆØ¶Ø©")}">
              <i class="bi bi-eye"></i>
            </a>
          </td>
        </tr>
      `;
      })
      .join("")
  );
}

function setPendingReportsBadge(value) {
  updateElementText("pendingReportsListBadge", formatNumber(value));
}

function renderPendingReportsList(kindergartens, summary) {
  const list = document.getElementById("pendingReportsList");
  if (!list) return;

  const totalFromSummary = safeNumber(summary.pending_daily_reports);
  setPendingReportsBadge(totalFromSummary);

  if (!Array.isArray(kindergartens)) {
    list.innerHTML = dashboardTemplate(
      '<div class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª</div>'
    );
    return;
  }

  const rows = kindergartens
    .filter((kg) => safeNumber(kg.pending_reports) > 0)
    .sort((a, b) => safeNumber(b.pending_reports) - safeNumber(a.pending_reports))
    .slice(0, 6);

  if (rows.length === 0) {
    list.innerHTML = dashboardTemplate(`
      <div class="text-center py-4 text-muted">
        <i class="bi bi-check-circle fs-1 d-block mb-2 opacity-25"></i>
        <span>Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙ‚Ø§Ø±ÙŠØ± Ù…Ø¹Ù„Ù‚Ø©</span>
      </div>
    `);
    return;
  }

  list.innerHTML = dashboardTemplate(
    rows
      .map((kg) => {
        return `
        <a href="/daily-reports" class="list-group-item list-group-item-action">
          <div class="d-flex justify-content-between align-items-center">
            <div>
              <div class="fw-semibold">${escapeHtml(kg.name_ar || kg.name_en || "-")}</div>
              <small class="text-muted">${dashboardLiteral("Ø¨Ø§Ù†ØªØ¸Ø§Ø± Ø§Ù„Ù…Ø±Ø§Ø¬Ø¹Ø©")}</small>
            </div>
            <span class="badge bg-warning rounded-pill">${formatNumber(kg.pending_reports || 0)}</span>
          </div>
        </a>
      `;
      })
      .join("")
  );
}

function translateAlertType(rawType) {
  const key = String(rawType || "")
    .trim()
    .toLowerCase();
  const labels = {
    alert: dashboardLiteral("ØªÙ†Ø¨ÙŠÙ‡"),
    license_expiry: dashboardLiteral("Ø§Ù†ØªÙ‡Ø§Ø¡ Ø§Ù„ØªØ±Ø®ÙŠØµ"),
    high_pending_applications: dashboardLiteral("Ø·Ù„Ø¨Ø§Øª ØªØ³Ø¬ÙŠÙ„ Ù…Ø¹Ù„Ù‚Ø©"),
    low_attendance: dashboardLiteral("Ø§Ù†Ø®ÙØ§Ø¶ Ø§Ù„Ø­Ø¶ÙˆØ±"),
    high_incidents: dashboardLiteral("Ø§Ø±ØªÙØ§Ø¹ Ø§Ù„Ø­ÙˆØ§Ø¯Ø«"),
    applications: dashboardLiteral("Ø·Ù„Ø¨Ø§Øª Ø§Ù„ØªØ³Ø¬ÙŠÙ„"),
    safety: dashboardLiteral("Ø§Ù„Ø³Ù„Ø§Ù…Ø©"),
    license: dashboardLiteral("Ø§Ù„ØªØ±Ø®ÙŠØµ"),
    compliance: dashboardLiteral("Ø§Ù„Ø§Ù…ØªØ«Ø§Ù„"),
  };
  return labels[key] || dashboardLiteral("ØªÙ†Ø¨ÙŠÙ‡");
}

function normalizeAlertPriority(rawPriority, rawSeverity) {
  const priority = String(rawPriority || "")
    .trim()
    .toLowerCase();
  if (priority) return priority;

  const severity = String(rawSeverity || "")
    .trim()
    .toLowerCase();
  if (severity === "critical") return "critical";
  if (severity === "error" || severity === "high") return "high";
  if (severity === "warning") return "medium";
  return "low";
}

function normalizeAlerts(alerts) {
  if (!Array.isArray(alerts)) return [];
  return alerts.map((alert, index) => {
    const resolvedType = alert.title || alert.type || dashboardLiteral("ØªÙ†Ø¨ÙŠÙ‡");
    const resolvedPriority = normalizeAlertPriority(alert.priority, alert.severity);
    return {
      id: alert.id || `${alert.type || "alert"}-${index}`,
      type: translateAlertType(resolvedType),
      message: String(
        alert.message || alert.details || dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙØ§ØµÙŠÙ„ Ù…ØªØ§Ø­Ø©.")
      ),
      priority: resolvedPriority,
      kindergartenId: alert.kindergarten_id || alert.entity_id || alert.kindergartenId || null,
    };
  });
}

function renderAlerts(rawAlerts) {
  const alerts = normalizeAlerts(rawAlerts);
  const section = document.getElementById("alertsSection");
  const container = document.getElementById("alertsContainer");

  updateElementText("alertCount", String(alerts.length));

  if (!section || !container) return;

  if (alerts.length === 0) {
    section.style.display = "none";
    container.innerHTML = dashboardTemplate(
      '<div class="text-muted text-center py-2">Ù„Ø§ ØªÙˆØ¬Ø¯ ØªÙ†Ø¨ÙŠÙ‡Ø§Øª Ù†Ø´Ø·Ø©</div>'
    );
    return;
  }

  const priorityClass = {
    critical: "danger",
    high: "warning",
    medium: "info",
    low: "secondary",
  };

  container.innerHTML = dashboardTemplate(
    alerts
      .map((alert) => {
        const klass = priorityClass[alert.priority] || "secondary";
        const actionUrl = alert.kindergartenId
          ? `/kindergartens/${alert.kindergartenId}`
          : "/dashboard";
        return `
        <div class="alert alert-${klass} mb-0">
          <div class="d-flex justify-content-between align-items-start gap-2">
            <div>
              <div class="fw-semibold">${escapeHtml(alert.type)}</div>
              <div class="small">${escapeHtml(alert.message)}</div>
            </div>
            <a href="${actionUrl}" class="btn btn-sm btn-outline-${klass}">${dashboardLiteral("ÙØªØ­")}</a>
          </div>
        </div>
      `;
      })
      .join("")
  );

  section.style.display = "block";
}

function destroyChartInstance(chartInstance) {
  if (chartInstance && typeof chartInstance.destroy === "function") {
    chartInstance.destroy();
  }
}

const NO_DATA_CHART_PLUGIN = {
  id: "dashboardNoDataOverlay",
  afterDraw(chart, _args, options) {
    const dataset = chart?.data?.datasets?.[0]?.data || [];
    const hasData = dataset.some((value) => safeNumber(value) > 0);
    if (hasData) return;

    const area = chart.chartArea;
    if (!area) return;

    const ctx = chart.ctx;
    ctx.save();
    ctx.fillStyle = "#6c757d";
    ctx.font = '13px "Segoe UI", Tahoma, sans-serif';
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(
      options?.message || dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…ØªØ§Ø­Ø©"),
      (area.left + area.right) / 2,
      (area.top + area.bottom) / 2
    );
    ctx.restore();
  },
};

const DOUGHNUT_SUMMARY_PLUGIN = {
  id: "dashboardDoughnutSummary",
  afterDraw(chart, _args, options) {
    if (chart?.config?.type !== "doughnut") return;
    const dataset = chart?.data?.datasets?.[0]?.data || [];
    const total = dataset.reduce((sum, value) => sum + safeNumber(value), 0);
    if (!total) return;

    const metaPoint = chart.getDatasetMeta(0)?.data?.[0];
    const centerX = metaPoint?.x;
    const centerY = metaPoint?.y;
    if (!Number.isFinite(centerX) || !Number.isFinite(centerY)) return;

    const ctx = chart.ctx;
    ctx.save();
    ctx.textAlign = "center";
    ctx.fillStyle = "#1f2937";
    ctx.font = '700 17px "Segoe UI", Tahoma, sans-serif';
    ctx.fillText(total.toLocaleString(dashboardCurrentLocale()), centerX, centerY - 2);
    ctx.fillStyle = "#6c757d";
    ctx.font = '12px "Segoe UI", Tahoma, sans-serif';
    ctx.fillText(
      options?.label || dashboardLiteral("Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø­Ø§Ù„Ø§Øª"),
      centerX,
      centerY + 15
    );
    ctx.restore();
  },
};

function renderAttendanceChart(series) {
  const canvas = document.getElementById("attendanceChart");
  if (!canvas || typeof Chart === "undefined") return;

  const list = Array.isArray(series) ? series : [];
  const labels = list.map((item) => formatDateLabel(item.date || item.label));
  const values = list.map((item) => safeNumber(item.count ?? item.value));

  DASHBOARD_STATE.attendanceSeries = list;
  const chartType = DASHBOARD_STATE.attendanceChartType === "bar" ? "bar" : "line";
  const context = canvas.getContext("2d");
  const areaGradient = context
    ? (() => {
        const gradient = context.createLinearGradient(0, 0, 0, 260);
        gradient.addColorStop(0, "rgba(13, 110, 253, 0.30)");
        gradient.addColorStop(1, "rgba(13, 110, 253, 0.02)");
        return gradient;
      })()
    : "rgba(13, 110, 253, 0.15)";

  destroyChartInstance(DASHBOARD_STATE.attendanceChart);
  DASHBOARD_STATE.attendanceChart = new Chart(canvas, {
    type: chartType,
    plugins: [NO_DATA_CHART_PLUGIN],
    data: {
      labels: labels.length > 0 ? labels : [dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª")],
      datasets: [
        {
          label: dashboardLiteral("Ø§Ù„Ø­Ø¶ÙˆØ±"),
          data: values.length > 0 ? values : [0],
          fill: chartType === "line",
          borderColor: "#0d6efd",
          backgroundColor: chartType === "line" ? areaGradient : "rgba(13, 110, 253, 0.45)",
          borderWidth: chartType === "line" ? 2.5 : 1,
          tension: 0.35,
          pointRadius: chartType === "line" ? 3.5 : 0,
          pointHoverRadius: chartType === "line" ? 5 : 0,
          pointBackgroundColor: "#0d6efd",
          borderRadius: chartType === "bar" ? 8 : 0,
          maxBarThickness: chartType === "bar" ? 36 : undefined,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 550, easing: "easeOutQuart" },
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: { display: false },
        dashboardNoDataOverlay: {
          message: dashboardLiteral(
            "Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ø­Ø¶ÙˆØ± Ø¶Ù…Ù† Ø§Ù„ÙØªØ±Ø© Ø§Ù„Ù…Ø®ØªØ§Ø±Ø©"
          ),
        },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.92)",
          titleColor: "#f8fafc",
          bodyColor: "#f8fafc",
          padding: 10,
          callbacks: {
            title(items) {
              return items?.[0]?.label || "";
            },
            label(context) {
              const value = safeNumber(context.parsed?.y ?? context.parsed);
              return `${dashboardText("dashboard.chart.attendance", "Ø§Ù„Ø­Ø¶ÙˆØ±", "Attendance")}: ${value.toLocaleString(dashboardCurrentLocale())}`;
            },
          },
        },
      },
      scales: {
        x: {
          ticks: { color: "#6c757d" },
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: {
            precision: 0,
            color: "#6c757d",
            callback(value) {
              return safeNumber(value).toLocaleString(dashboardCurrentLocale());
            },
          },
          grid: { color: "rgba(108, 117, 125, 0.15)" },
        },
      },
    },
  });
}

function renderEnrollmentChart(enrollmentMap) {
  const canvas = document.getElementById("enrollmentPieChart");
  if (!canvas || typeof Chart === "undefined") return;

  const map = enrollmentMap && typeof enrollmentMap === "object" ? enrollmentMap : {};
  const entries = Object.entries(map);
  const labels = entries.map(([status]) => statusLabel(status));
  const values = entries.map(([, count]) => safeNumber(count));
  const hasData = values.some((value) => value > 0);

  destroyChartInstance(DASHBOARD_STATE.enrollmentChart);
  DASHBOARD_STATE.enrollmentChart = new Chart(canvas, {
    type: "doughnut",
    plugins: [NO_DATA_CHART_PLUGIN, DOUGHNUT_SUMMARY_PLUGIN],
    data: {
      labels: hasData ? labels : [dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª")],
      datasets: [
        {
          data: hasData ? values : [0],
          backgroundColor: hasData
            ? ["#0d6efd", "#16a34a", "#f59e0b", "#dc2626", "#64748b", "#0ea5e9"]
            : ["#dee2e6"],
          borderWidth: 2,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      animation: { duration: 650, easing: "easeOutQuart" },
      plugins: {
        dashboardNoDataOverlay: {
          message: dashboardLiteral("Ù„Ø§ ØªÙˆØ¬Ø¯ Ø­Ø§Ù„Ø§Øª ØªØ³Ø¬ÙŠÙ„ Ù…ØªØ§Ø­Ø©"),
        },
        dashboardDoughnutSummary: { label: dashboardLiteral("Ø¥Ø¬Ù…Ø§Ù„ÙŠ Ø§Ù„Ø­Ø§Ù„Ø§Øª") },
        legend: {
          position: "bottom",
          labels: {
            usePointStyle: true,
            boxWidth: 10,
            boxHeight: 10,
            padding: 14,
          },
        },
        tooltip: {
          backgroundColor: "rgba(17, 24, 39, 0.92)",
          titleColor: "#f8fafc",
          bodyColor: "#f8fafc",
          padding: 10,
          callbacks: {
            label(context) {
              const dataset = context.dataset?.data || [];
              const total = dataset.reduce((sum, item) => sum + safeNumber(item), 0);
              const value = safeNumber(context.parsed);
              const percentage = total > 0 ? (value / total) * 100 : 0;
              return `${context.label}: ${value.toLocaleString(dashboardCurrentLocale())} (${percentage.toFixed(1)}%)`;
            },
          },
        },
      },
    },
  });
}

function bindChartTypeToggles() {
  const buttons = document.querySelectorAll("[data-chart-type]");
  if (!buttons.length) return;

  buttons.forEach((button) => {
    button.addEventListener("click", (event) => {
      const selectedType = event.currentTarget?.dataset?.chartType;
      if (!selectedType || !["line", "bar"].includes(selectedType)) return;

      DASHBOARD_STATE.attendanceChartType = selectedType;
      buttons.forEach((btn) => btn.classList.remove("active"));
      event.currentTarget.classList.add("active");
      renderAttendanceChart(DASHBOARD_STATE.attendanceSeries || []);
    });
  });
}

function buildKpiRows(payload) {
  const rows = [];
  for (const definition of KPI_DEFINITIONS) {
    const card = payload?.[definition.key];
    if (!card || typeof card !== "object") continue;

    const value = safeNumber(card.value ?? card.current_value);
    const unit = card.unit != null ? String(card.unit) : definition.unit;
    const band =
      normalizeBand(card.band || card.rating || card.status) || inferBand(definition.key, value);
    const trend = normalizeTrend(card.trend_indicator || card.trend);
    const explanation = card.explanation?.ar || card.explanation?.en || card.tooltip || "";
    const managerNote = card.manager_note?.ar || card.manager_note?.en || "";
    const actions = Array.isArray(card.action_items) ? card.action_items : [];

    rows.push({
      key: definition.key,
      label: typeof definition.label === "function" ? definition.label() : definition.label,
      value,
      unit,
      band,
      trend,
      explanation,
      managerNote,
      actions,
    });
  }
  return rows;
}

function renderKpiCards(kpis) {
  const container = document.getElementById("kpiCardsContainer");
  if (!container) return;

  if (!Array.isArray(kpis) || kpis.length === 0) {
    container.innerHTML = dashboardTemplate(
      '<div class="col-12 text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…Ø¤Ø´Ø±Ø§Øª Ø­Ø§Ù„ÙŠØ§Ù‹</div>'
    );
    return;
  }

  container.innerHTML = dashboardTemplate(
    kpis
      .map((kpi) => {
        const color = BAND_BOOTSTRAP[kpi.band] || "secondary";
        const bandText = (BAND_LABEL[kpi.band] || BAND_LABEL.neutral)();
        const formattedValue = Number.isFinite(kpi.value) ? formatOneDecimal(kpi.value) : "--";
        const unit = kpi.unit || "";
        const hasActions = Array.isArray(kpi.actions) && kpi.actions.length > 0;

        return `
        <div class="col-md-6 col-lg-4">
          <div class="kpi-card card border-0 shadow-sm h-100" data-status="${kpi.band}" style="border-radius: 16px;">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start mb-2">
                <h6 class="text-muted mb-0">${escapeHtml(kpi.label)}</h6>
                <span class="badge bg-${color}">${bandText}</span>
              </div>
              <div class="display-6 fw-bold text-${color}">${formattedValue}${escapeHtml(unit)}</div>
              <div class="text-muted small mt-1">${dashboardLiteral("Ø§Ù„Ø§ØªØ¬Ø§Ù‡")}: ${trendSymbol(kpi.trend)}</div>
              ${
                hasActions
                  ? `<button type="button" class="btn btn-sm btn-outline-${color} mt-3" onclick="openKpiActionItems('${kpi.key}')">${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª")}</button>`
                  : ""
              }
            </div>
          </div>
        </div>
      `;
      })
      .join("")
  );
}

function renderKpiTable(kpis) {
  const tableBody = document.getElementById("kpiTableBody");
  if (!tableBody) return;

  if (!Array.isArray(kpis) || kpis.length === 0) {
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="5" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¨ÙŠØ§Ù†Ø§Øª Ù…Ø¤Ø´Ø±Ø§Øª Ø­Ø§Ù„ÙŠØ§Ù‹</td></tr>'
    );
    return;
  }

  tableBody.innerHTML = dashboardTemplate(
    kpis
      .map((kpi) => {
        const color = BAND_BOOTSTRAP[kpi.band] || "secondary";
        const value = Number.isFinite(kpi.value) ? formatOneDecimal(kpi.value) : "--";
        const actionsLabel =
          Array.isArray(kpi.actions) && kpi.actions.length > 0
            ? `<button type="button" class="btn btn-sm btn-outline-${color}" onclick="openKpiActionItems('${kpi.key}')">${dashboardLiteral("Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª")}</button>`
            : "-";

        return `
        <tr>
          <td>${escapeHtml(kpi.label)}</td>
          <td class="fw-bold">${value}${escapeHtml(kpi.unit || "")}</td>
          <td><span class="badge bg-${color}">${(BAND_LABEL[kpi.band] || BAND_LABEL.neutral)()}</span></td>
          <td>${trendSymbol(kpi.trend)}</td>
          <td>${actionsLabel}</td>
        </tr>
      `;
      })
      .join("")
  );
}

function renderKpiStatusCounts(kpis, alertCount) {
  const excellent = kpis.filter((k) => k.band === "green").length;
  const caution = kpis.filter((k) => k.band === "amber").length;
  const critical = kpis.filter((k) => k.band === "red").length;

  updateElementText("excellentCount", String(excellent));
  updateElementText("cautionCount", String(caution));
  updateElementText("criticalCount", String(critical));

  if (typeof alertCount === "number") {
    updateElementText("alertCount", String(alertCount));
  }
}

function renderKpiExplanations(kpis) {
  const container = document.getElementById("explanationsContainer");
  if (!container) return;

  if (!Array.isArray(kpis) || kpis.length === 0) {
    container.innerHTML = dashboardTemplate(
      '<p class="text-muted mb-0">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø´Ø±ÙˆØ­Ø§Øª Ù…ØªØ§Ø­Ø© Ù„Ù„Ù…Ø¤Ø´Ø±Ø§Øª.</p>'
    );
    return;
  }

  container.innerHTML = dashboardTemplate(
    kpis
      .map((kpi) => {
        return `
        <div class="item">
          <h6 class="mb-1">${escapeHtml(kpi.label)}</h6>
          <p class="mb-1">${escapeHtml(kpi.explanation || dashboardLiteral("Ù„Ø§ ÙŠÙˆØ¬Ø¯ Ø´Ø±Ø­ Ù…ØªØ§Ø­."))}</p>
          ${
            kpi.managerNote
              ? `<small class="text-muted">${escapeHtml(kpi.managerNote)}</small>`
              : ""
          }
        </div>
      `;
      })
      .join("")
  );
}

function renderKpiSummaryRow(payload) {
  const attendanceValue = safeNumber(payload?.attendance_rate?.value);
  const ratioValue = safeNumber(payload?.ratio_compliance?.value);
  const incidentValue = safeNumber(payload?.incident_rate?.value);
  const governanceValue = safeNumber(payload?.overall_gcei?.value);

  updateElementText("kpiAttendance", `${formatOneDecimal(attendanceValue)}%`);
  updateElementText("kpiRatioCompliance", `${formatOneDecimal(ratioValue)}%`);
  updateElementText("kpiIncidentRate", formatOneDecimal(incidentValue));

  const band =
    normalizeBand(payload?.overall_gcei?.band) || inferBand("overall_gcei", governanceValue);
  const governanceBand = document.getElementById("governanceBand");
  if (governanceBand) {
    governanceBand.className = `badge fs-4 px-4 py-2 bg-${BAND_BOOTSTRAP[band] || "secondary"}`;
    governanceBand.textContent = (BAND_LABEL[band] || BAND_LABEL.neutral)();
  }

  updateElementText("governanceScore", `${formatOneDecimal(governanceValue)}%`);
}

async function loadKPIs(prefetchedData = null) {
  try {
    const data =
      prefetchedData ||
      (await dashboardFetch(
        buildUrlWithParams(DASHBOARD_API.admin.kpis, {
          ...getDashboardDateRange(),
          locale: dashboardCurrentLang(),
        })
      ));
    const kpis = buildKpiRows(data);

    DASHBOARD_STATE.kpis = kpis;
    renderKpiCards(kpis);
    renderKpiTable(kpis);
    renderKpiStatusCounts(kpis, Array.isArray(data?.alerts) ? data.alerts.length : undefined);
    renderKpiExplanations(kpis);
    renderKpiSummaryRow(data);
  } catch (error) {
    console.error("Error loading KPIs:", error);
    renderKpiCards([]);
    renderKpiTable([]);
  }
}

function openKpiActionItems(metricKey) {
  const metric = DASHBOARD_STATE.kpis.find((kpi) => kpi.key === metricKey);
  const title = document.getElementById("actionModalTitle");
  const container = document.getElementById("actionItemsContainer");
  const modalElement = document.getElementById("kpiActionModal");

  if (!title || !container || !modalElement) return;

  title.textContent = metric
    ? `${dashboardLiteral("Ø®Ø·Ø© Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡")}: ${metric.label}`
    : dashboardLiteral("Ø®Ø·Ø© Ø§Ù„Ø¥Ø¬Ø±Ø§Ø¡");

  if (!metric || !Array.isArray(metric.actions) || metric.actions.length === 0) {
    container.innerHTML = dashboardTemplate(
      '<p class="text-muted mb-0">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø¥Ø¬Ø±Ø§Ø¡Ø§Øª Ù…Ù‚ØªØ±Ø­Ø© Ù„Ù‡Ø°Ø§ Ø§Ù„Ù…Ø¤Ø´Ø±.</p>'
    );
  } else {
    container.innerHTML = dashboardTemplate(
      metric.actions
        .map((item, index) => {
          const priority = String(item.priority || "medium").toLowerCase();
          const priorityLabel =
            priority === "high"
              ? dashboardLiteral("Ø¹Ø§Ù„ÙŠØ©")
              : priority === "medium"
                ? dashboardLiteral("Ù…ØªÙˆØ³Ø·Ø©")
                : dashboardLiteral("Ù…Ù†Ø®ÙØ¶Ø©");
          const actionText = item.ar || item.action || item.en || dashboardLiteral("Ø¥Ø¬Ø±Ø§Ø¡");
          const detail = item.ar || item.en || "";
          return `
          <div class="border rounded p-3 mb-2">
            <div class="d-flex justify-content-between align-items-start gap-2">
              <div>
                <div class="fw-semibold">${index + 1}. ${escapeHtml(actionText)}</div>
                ${detail ? `<div class="small text-muted mt-1">${escapeHtml(detail)}</div>` : ""}
              </div>
              <span class="badge bg-${priority === "high" ? "danger" : priority === "medium" ? "warning" : "info"}">${escapeHtml(priorityLabel)}</span>
            </div>
          </div>
        `;
        })
        .join("")
    );
  }

  new bootstrap.Modal(modalElement).show();
}

window.openKpiActionItems = openKpiActionItems;
window.loadDashboard = loadDashboard;
window.renderValidationDetails = renderValidationDetails;

function ensureDashboardDateRangeDefaults() {
  if (window.dashboardDateRange?.start && window.dashboardDateRange?.end) return;
  const today = new Date();
  const start = new Date(today.getFullYear(), today.getMonth(), 1);
  const end = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const toIso = (value) => value.toISOString().slice(0, 10);
  window.dashboardDateRange = {
    range: "month",
    start: toIso(start),
    end: toIso(end),
  };
}

async function loadKindergartensOverview() {
  const tableBody = document.getElementById("kindergartensOverviewTable");
  if (!tableBody) return;

  try {
    const data = await dashboardFetch(DASHBOARD_API.admin.kindergartens);
    const kindergartens = data.kindergartens || data.items || data || [];

    if (!Array.isArray(kindergartens) || kindergartens.length === 0) {
      tableBody.innerHTML = dashboardTemplate(
        '<tr><td colspan="8" class="text-center py-4 text-muted">Ù„Ø§ ØªÙˆØ¬Ø¯ Ø±ÙˆØ¶Ø§Øª</td></tr>'
      );
      return;
    }

    tableBody.innerHTML = dashboardTemplate(
      kindergartens
        .map((kg) => {
          const status = String(kg.status || "").toUpperCase();
          const statusClass = status === "ACTIVE" ? "success" : "secondary";
          return `
          <tr>
            <td>${escapeHtml(kg.name_ar || kg.name_en || "-")}</td>
            <td><span class="badge bg-${statusClass}">${statusLabel(status)}</span></td>
            <td>${formatNumber(kg.enrolled_count || 0)}</td>
            <td>${formatNumber(kg.attendance_today || 0)}</td>
            <td>${formatNumber(kg.pending_reports || 0)}</td>
            <td>${formatOneDecimal(kg.capacity_utilization || 0)}%</td>
            <td><span class="badge bg-${kg.license_valid ? "success" : "danger"}">${kg.license_valid ? dashboardLiteral("Ø³Ø§Ø±ÙŠ") : dashboardLiteral("Ù…Ù†ØªÙ‡ÙŠ")}</span></td>
            <td>
              <a href="/kindergartens/${kg.id}" class="btn btn-sm btn-outline-primary" aria-label="${dashboardLiteral("Ø¹Ø±Ø¶ Ø§Ù„Ø±ÙˆØ¶Ø©")}">
                <i class="bi bi-eye"></i>
              </a>
            </td>
          </tr>
        `;
        })
        .join("")
    );
  } catch (error) {
    console.error("Error loading kindergartens:", error);
    tableBody.innerHTML = dashboardTemplate(
      '<tr><td colspan="8" class="text-center py-4 text-danger">ØªØ¹Ø°Ø± ØªØ­Ù…ÙŠÙ„ Ø¨ÙŠØ§Ù†Ø§Øª Ø§Ù„Ø±ÙˆØ¶Ø§Øª</td></tr>'
    );
  }
}

document.addEventListener("DOMContentLoaded", () => {
  ensureDashboardDateRangeDefaults();
  bindChartTypeToggles();
  renderValidationDetails();
  loadDashboard();
});
