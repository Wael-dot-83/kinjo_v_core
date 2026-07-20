
// UX Error Banner & Tooltips Handlers
window.showDataErrorBanner = function(timeStr) {
    const banner = document.getElementById('offlineBanner');
    if (banner) {
        banner.classList.remove('hidden');
        document.getElementById('offlineTime').textContent = timeStr || new Date().toLocaleTimeString();
    }
};

window.hideDataErrorBanner = function() {
    const banner = document.getElementById('offlineBanner');
    if (banner) {
        banner.classList.add('hidden');
    }
};

// safeChartData() is provided globally by chart_utils.js (loaded before this script).

function adminAnalyticsText(arText, enText) {
  const lang =
    window.AdminI18n?.getCurrentLanguage?.().code ||
    localStorage.getItem("admin_language") ||
    localStorage.getItem("kinjo_lang") ||
    document.documentElement.lang ||
    "ar";
  return String(lang).toLowerCase().startsWith("en") ? enText : arText;
}

function adminAnalyticsEscape(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[char]);
}

function adminAnalyticsInternalLink(value, fallback = "/admin/analytics") {
  const link = String(value || "");
  return /^\/admin(?:\/|$)/.test(link) ? link : fallback;
}

function adminAnalyticsIcon(value, fallback = "bi-info-circle") {
  const icon = String(value || "");
  return /^bi-[a-z0-9-]+$/.test(icon) ? icon : fallback;
}

var lastDashboardData = null;
let scenarioData = null;
var fetchWithAuth = window.fetchWithAuth || async function adminAnalyticsFetchFallback(url, options) {
  const opts = Object.assign({ credentials: "same-origin" }, options || {});
  const method = (opts.method || "GET").toUpperCase();
  opts.headers = Object.assign({ "Accept": "application/json" }, opts.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = (window.CSRF_CONFIG && window.CSRF_CONFIG.cookieName && window.AuthStorage && window.AuthStorage.getCookie && window.AuthStorage.getCookie(window.CSRF_CONFIG.cookieName)) ||
                      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    if (csrfToken) {
      opts.headers["X-CSRF-Token"] = csrfToken;
    }
  }
  const response = await fetch(url, opts);
  if (response.status === 401) {
    window.location.href = "/login?redirect=" + encodeURIComponent(window.location.pathname);
    return null;
  }
  if (!response.ok) {
    throw new Error(response.statusText || `Request failed with status ${response.status}`);
  }
  return response;
};

function adminAnalyticsHasChart() {
  return typeof window.Chart === "function" && typeof window.safeChartData === "function";
}

function adminAnalyticsUnavailableText() {
  return adminAnalyticsText("غير متاح", "Unavailable");
}

function adminAnalyticsNoDataText() {
  return adminAnalyticsText("لا توجد بيانات متاحة للفترة المحددة", "No data available for the selected period");
}

document.addEventListener("DOMContentLoaded", function () {
  // Set default date range (Current Month)
  const today = new Date();
  // Explicitly set to current month start and end
  const currentYear = today.getFullYear();
  const currentMonth = today.getMonth();
  const firstDay = new Date(currentYear, currentMonth, 1);
  const lastDay = new Date(currentYear, currentMonth + 1, 0); // Last day of current month

  // Format dates as YYYY-MM-DD
  const formatDate = (d) => { const year = d.getFullYear(); const month = String(d.getMonth() + 1).padStart(2, "0"); const day = String(d.getDate()).padStart(2, "0"); return `${year}-${month}-${day}`; };

  const startInput = document.getElementById("periodStart");
  const endInput = document.getElementById("periodEnd");
  const govSelect = document.getElementById("governorateFilter");
  const supervisorHint = document.getElementById("supervisorScopeHint");

  if (startInput && endInput) {
    // Ensure start date is before end date
    const startDate = formatDate(firstDay);
    const endDate = formatDate(today); // Use today instead of lastDay to match data

    startInput.value = startDate;
    endInput.value = endDate;

    // Sync from global filter state
    if (window.AnalyticsFilterState) {
      var saved = window.AnalyticsFilterState.getState();
      var pStart = document.getElementById('periodStart');
      var pEnd = document.getElementById('periodEnd');
      var govFilter = document.getElementById('governorateFilter');

      if (saved.periodStart && pStart) pStart.value = saved.periodStart;
      if (saved.periodEnd && pEnd) pEnd.value = saved.periodEnd;
      if (saved.governorate && govFilter) {
        govFilter.value = saved.governorate;
      }
    }

    // Initial load
    loadAdminAnalytics();
  }

  // Load governorates for filter
  if (govSelect) {
    while (govSelect.options.length > 1) {
      govSelect.remove(1);
    }

    // Public reference data — use a plain cookie fetch (not the auth-gated
    // fetchWithAuth, which redirects to /login when no localStorage token is
    // present, e.g. under cookie-only sessions and E2E).
    fetch("/api/locations/jordan/governorates", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then((res) => {
        if (!res || !res.ok) return;
        return res.json();
      })
      .then((data) => {
        if (!data) return;
        const locale = adminAnalyticsLocale();
        // The unified locations API wraps the list in an envelope:
        // { data: { governorates: [...] } }. Fall back to a flat shape too.
        const govList =
          (data.data && data.data.governorates) || data.governorates || [];
        govList.forEach((g) => {
          const normalized = normalizeGovernorateOption(g, locale);
          if (!normalized.value || !normalized.label) return;
          const opt = document.createElement("option");
          opt.value = normalized.value;
          opt.textContent = normalized.label;
          govSelect.appendChild(opt);
        });

        // Show scope hint for supervisors with more than one allowed option
        const userRole = govSelect.dataset.userRole;
        const optionCount = govSelect.options?.length || 0;
        if (userRole === "SUPERVISOR" && optionCount > 2 && supervisorHint) {
          supervisorHint.classList.remove("d-none");
        }
      })
      .catch(() => {});
    govSelect.addEventListener("change", () => {
      if (window.AnalyticsFilterState) {
        window.AnalyticsFilterState.syncFromDOM();
        window.AnalyticsFilterState.setState({ source: 'dashboard' });
      }
      loadAdminAnalytics();
    });
  }

  // Subscribe to global filter state changes from other views
  if (window.AnalyticsFilterState) {
    window.AnalyticsFilterState.subscribe(function (newState) {
      if (newState.source === 'dashboard') return;

      var pStart = document.getElementById('periodStart');
      var pEnd = document.getElementById('periodEnd');
      var govFilter = document.getElementById('governorateFilter');

      var needsReload = false;

      if (newState.periodStart && pStart && pStart.value !== newState.periodStart) {
        pStart.value = newState.periodStart;
        needsReload = true;
      }
      if (newState.periodEnd && pEnd && pEnd.value !== newState.periodEnd) {
        pEnd.value = newState.periodEnd;
        needsReload = true;
      }
      if (govFilter && newState.governorate !== undefined && govFilter.value !== newState.governorate) {
        govFilter.value = newState.governorate;
        needsReload = true;
      }

      if (needsReload) {
        loadAdminAnalytics();
      }
    });
  }

  // Setup Report Form Date Inputs
  const reportStart = document.getElementById("startDate");
  const reportEnd = document.getElementById("endDate");
  if (reportStart && reportEnd) {
    reportStart.value = formatDate(firstDay);
    reportEnd.value = formatDate(today);
  }
});

let governanceChart = null;
let trendChartInstance = null;
let governorateTableSorter = null;
let chartAnnotations = null;

// =============================================================================
// Unified Translation Dictionary — Ensures linguistic consistency
// =============================================================================
const ADMIN_TRANSLATIONS = {
  pageTitles: {
    overview: { ar: "نظرة عامة", en: "Overview" },
    registrations: { ar: "التسجيلات", en: "Registrations" },
    regions: { ar: "المناطق", en: "Regions" },
    governance: { ar: "الحوكمة", en: "Governance" },
    aiPredictions: { ar: "الذكاء والتنبؤات", en: "AI & Predictions" }
  },
  metrics: {
    facilities: { ar: "إجمالي المرافق", en: "Total Facilities" },
    children: { ar: "الأطفال المسجلون", en: "Enrolled Children" },
    attendance: { ar: "الحضور اليومي", en: "Daily Attendance" },
    incidents: { ar: "معدل الحوادث", en: "Incident Rate" },
    governanceScore: { ar: "متوسط الحوكمة", en: "Governance Score" },
    conversion: { ar: "معدل الإكمال", en: "Completion Rate" }
  },
  statuses: {
    excellent: { ar: "ممتاز", en: "Excellent" },
    good: { ar: "جيد", en: "Good" },
    average: { ar: "متوسط", en: "Average" },
    needsImprovement: { ar: "يحتاج تحسين", en: "Needs Improvement" }
  },
  timeframes: {
    vsPrevious: { ar: "عن الفترة السابقة", en: "vs previous period" },
    noChange: { ar: "لا تغيير عن الفترة السابقة", en: "No change vs previous period" },
    improved: { ar: "تحسن", en: "Improved" },
    declined: { ar: "انخفاض", en: "Declined" }
  }
};

function t(key, subkey) {
  const lang = adminAnalyticsLocale();
  const isEnglish = lang.startsWith("en");
  const category = ADMIN_TRANSLATIONS[key];
  if (!category) return key;
  const entry = category[subkey];
  if (!entry) return subkey;
  return isEnglish ? entry.en : entry.ar;
}

// Safe translate wrapper for AdminI18n
function safeTranslate(key) {
  if (typeof window.AdminI18n?.translate === 'function') {
    const result = window.AdminI18n.translate(key);
    return typeof result === 'string' ? result : key;
  }
  return key;
}

function adminAnalyticsLocale() {
  return adminAnalyticsText("ar-JO", "en-US");
}

const SEVERITY_LABELS = {
  LOW: { ar: "منخفض", en: "Low" },
  MEDIUM: { ar: "متوسط", en: "Medium" },
  HIGH: { ar: "عالي", en: "High" },
  CRITICAL: { ar: "حرج", en: "Critical" },
};

function formatAnomalySeverity(severity) {
  const labels = SEVERITY_LABELS[severity] || { ar: severity, en: severity };
  return adminAnalyticsText(labels.ar, labels.en);
}

const METRIC_TYPE_LABELS = {
  attendance: { ar: "الحضور", en: "Attendance" },
  incidents: { ar: "الحوادث", en: "Incidents" },
  enrollment: { ar: "الالتحاق", en: "Enrollment" },
};

function formatMetricType(metricType) {
  const labels = METRIC_TYPE_LABELS[metricType] || { ar: metricType.replace(/_/g, " "), en: metricType.replace(/_/g, " ") };
  return adminAnalyticsText(labels.ar, labels.en);
}

function normalizeGovernorateOption(option, locale) {
  if (typeof option === "string") {
    const text = option.trim();
    return text ? { value: text, label: text } : { value: "", label: "" };
  }

  if (!option || typeof option !== "object") {
    return { value: "", label: "" };
  }

  const isEnglish = String(locale || "").toLowerCase().startsWith("en");
  const value = option.key ?? option.id ?? option.value ?? option.name ?? option.label ?? "";
  const label = option.name_ar || option.name_en || option.name || option.label || value || "";

  if (value == null || label == null || typeof value === "object" || typeof label === "object") {
    return { value: "", label: "" };
  }

  const valueText = String(value).trim();
  const labelValue = isEnglish && option.name_en ? option.name_en : label;
  const labelText = String(labelValue ?? label ?? "").trim();

  if (!valueText || !labelText || valueText === "[object Object]" || labelText === "[object Object]") {
    return { value: "", label: "" };
  }

  return { value: valueText, label: labelText };
}

function adminAnalyticsLiteral(value) {
  const raw = String(value ?? "");
  if (!raw) {
    return "";
  }
  let result = raw;
  if (typeof window.AdminI18n?.replaceLiteralSegments === "function") {
    result = window.AdminI18n.replaceLiteralSegments(raw);
  } else if (typeof window.AppI18n?.replaceLiteralSegments === "function") {
    result = window.AppI18n.replaceLiteralSegments(raw);
  }
  return typeof window.escapeHtml === "function" ? window.escapeHtml(result) : result;
}

async function loadAdminAnalytics(retryCount = 0) {
  // Push current filter values to global state
  if (window.AnalyticsFilterState) {
    var pStart = document.getElementById('periodStart');
    var pEnd = document.getElementById('periodEnd');
    var govFilter = document.getElementById('governorateFilter');
    window.AnalyticsFilterState.setState({
      periodStart: pStart ? pStart.value : undefined,
      periodEnd: pEnd ? pEnd.value : undefined,
      governorate: govFilter ? govFilter.value : 'all',
      source: 'dashboard'
    });
  }

  const maxRetries = 2;
  const start = document.getElementById("periodStart")?.value || "";
  const end = document.getElementById("periodEnd")?.value || "";
  const gov = document.getElementById("governorateFilter")?.value || "";
  const btn = document.getElementById("refreshBtn");

  if (!start || !end) {
    showToast(
      adminAnalyticsText("يرجى تحديد تاريخ البداية والنهاية", "Please select start and end dates"),
      "warning"
    );
    return;
  }

  // Validate date range client-side
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (startDate > endDate) {
    showToast(
      adminAnalyticsText(
        "خطأ: تاريخ البداية يجب أن يكون قبل تاريخ النهاية",
        "Error: start date must be before end date"
      ),
      "error"
    );
    hideSkeletonLoaders();
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="bi bi-arrow-clockwise me-1"></i>${adminAnalyticsText("تحديث", "Refresh")}`;
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<i class="bi bi-arrow-clockwise me-1"></i>${adminAnalyticsText("جاري التحديث...", "Refreshing...")}`;
  }

  showSkeletonLoaders();

  try {
    // Add timeout to prevent indefinite loading
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 60000); // 60 second timeout

    const response = await fetchWithAuth(
      `/api/analytics/dashboard-data?period_start=${start}&period_end=${end}${
        gov ? `&governorate=${encodeURIComponent(gov)}` : ""
      }`,
      { signal: controller.signal }
    );

    clearTimeout(timeoutId);

    if (!response) return;

    const data = await response.json();

    // Phase 1: Critical data — KPIs + the charts that come bundled in the
    // single dashboard-data payload. Render these synchronously so the user
    // sees the headline numbers and core visuals as soon as possible.
    lastDashboardData = data;
    updateNetworkSummary(data.network_summary);
    updateTrendCharts(data.attendance_trend, data.incident_trend);
    updateGovernorateBreakdown(data.governorate_breakdown);
    updateRiskRadar(data.risk_radar);
    const dist = data.governance_distribution || {};
    updateGovernanceChart(dist.green || 0, dist.amber || 0, dist.red || 0);

    // Critical payload is on screen — drop the skeleton states.
    hideSkeletonLoaders();

    loadInsights();
    loadActionQueue();

    const scopeType = gov ? "GOVERNORATE" : "NETWORK";
    const scopeId = gov || null;

    // Success feedback, timestamp, and the v2 enhancement event fire once the
    // critical view is rendered rather than after every secondary widget.
    showToast(
      adminAnalyticsText("تم تحديث البيانات بنجاح", "Data refreshed successfully"),
      "success"
    );
    updateLastUpdatedTimestamp();

    // Fire event for v2 enhancement layer
    document.dispatchEvent(new CustomEvent('analyticsDataLoaded', {
      detail: Object.assign({}, data, {
        __period__: { start: start, end: end }
      })
    }));

    // Phase 2: Secondary widgets — heavier analytical views. These are
    // independent of each other and already have their own internal
    // try/catch, so a single slow call can't stall the rest. Scheduled on
    // idle so they never compete with the critical render above.
    scheduleIdle(() => loadSecondaryWidgets(start, end, scopeType, scopeId), 100);

    // Phase 3: Tertiary widgets — supporting panels (alerts, data quality,
    // targets, benchmarks, recommendations). Lowest priority; loaded last.
    scheduleIdle(() => loadTertiaryWidgets(), 200);
  } catch (error) {
    console.error("Analytics load error:", error);

    // Show cached "stale" state if we have data, else error
    if (window.lastDashboardData) {
      showToast(adminAnalyticsText("يتم عرض البيانات المخزنة مؤقتاً لتعذر الاتصال بالخادم", "Showing cached data. Server unreachable."), "warning");
    } else {
      const overlay = document.getElementById("trendChartOverlay");
      const errorDiv = document.getElementById("trendChartError");
      if (overlay) overlay.classList.add("d-none");
      if (errorDiv) {
        errorDiv.classList.add("show");
        // The overlay's base ".hidden" class (opacity:0; pointer-events:none)
        // must be dropped or the retry button is present but not clickable.
        errorDiv.classList.remove("hidden");
        errorDiv.innerHTML = `
          <i class="bi bi-exclamation-circle text-danger fs-1"></i>
          <p class="mt-2 text-danger"> فشل تحميل البيانات. </p>
          <button class="btn btn-primary btn-sm mt-2" onclick="loadAdminAnalytics()">إعادة المحاولة</button>
        `;
      }
    }
    
    // Handle timeout
    if (error.name === "AbortError") {
      console.error("Request timed out");
      if (retryCount < maxRetries) {
        setTimeout(() => loadAdminAnalytics(retryCount + 1), 2000);
        return;
      }
      showToast(
        adminAnalyticsText(
          "انتهت مهلة الطلب. يرجى المحاولة لاحقاً",
          "Request timed out. Please try again later"
        ),
        "error"
      );
      return;
    }

    // Retry logic
    if (retryCount < maxRetries && !error.message.includes("Invalid date range")) {
      setTimeout(() => loadAdminAnalytics(retryCount + 1), 1000 * (retryCount + 1)); // Exponential backoff
      return;
    }

    const userMessage = error.message.includes("Invalid date range")
      ? adminAnalyticsText(
          "يرجى التأكد من صحة نطاق التاريخ المحدد",
          "Please verify the selected date range"
        )
      : error.message.includes("500")
        ? adminAnalyticsText(
            "خطأ في الخادم. يرجى المحاولة لاحقاً",
            "Server error. Please try again later"
          )
        : adminAnalyticsText(
            "حدث خطأ في تحميل البيانات. يرجى المحاولة مرة أخرى.",
            "Failed to load data. Please try again"
          );
    showToast(userMessage, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = `<i class="bi bi-arrow-clockwise me-1"></i>${adminAnalyticsText("تحديث", "Refresh")}`;
    }
    hideSkeletonLoaders();
  }
}

// Run a non-critical task during browser idle time. requestIdleCallback is
// heavily throttled in backgrounded/hidden tabs (and in headless), where even its
// own `timeout` can be starved — so we also arm a guaranteed setTimeout fallback
// and run whichever fires first (once). Falls back to a plain timeout when
// requestIdleCallback is unavailable (older Safari / some embedded webviews).
function scheduleIdle(task, fallbackDelay = 100) {
  if (typeof window.requestIdleCallback === "function") {
    let ran = false;
    const run = () => { if (!ran) { ran = true; task(); } };
    window.requestIdleCallback(run, { timeout: 2000 });
    setTimeout(run, 2500);
    return;
  }
  return setTimeout(task, fallbackDelay);
}

// Phase 2: secondary analytical widgets. Each fetches its own data and owns its
// own DOM subtree, and each already has its own internal try/catch, so we use
// allSettled (not Promise.all) and never await them in the critical path.
async function loadSecondaryWidgets(start, end, scopeType, scopeId) {
  await Promise.allSettled([
    loadComparativeAnalysis(start, end),
    loadPredictiveInsights(start, end, scopeType, scopeId),
    loadAnomalies(start, end, scopeType, scopeId),
    loadRegistrationAnalytics(),
    loadChartAnnotations(),
    loadTargetProgress(),
    loadPredictiveAlerts(),
    loadNarrativeSummary(),
  ]);
  await loadScenarios();
}

// Phase 3: tertiary supporting panels (alerts, data quality, targets,
// benchmarks, recommendations). Lowest priority, loaded last on idle.
async function loadTertiaryWidgets() {
  await Promise.allSettled([
    loadAlerts(),
    loadDataQuality(),
    loadTargets(),
    loadBenchmarks(),
    loadRecommendations(),
    loadDataLineage(),
  ]);
}

function showSkeletonLoaders() {
  // Show skeleton for KPI cards
  document
    .querySelectorAll("#totalKg, #totalChildren, #avgAttendance, #incidentRate, #enrollmentRate")
    .forEach((el) => {
      el.innerHTML = '<div class="skeleton-text w-50"></div>';
    });
  const erBar = document.querySelector("#enrollmentRateBar");
  if (erBar) erBar.style.width = "0%";
  const kgGrowth = document.querySelector("#kpiKgGrowth");
  if (kgGrowth) kgGrowth.innerHTML = '<div class="skeleton-text w-75"></div>';

  // Show skeleton for registration KPI cards
  document
    .querySelectorAll("#regTotalApplications, #regNewApplications, #regApproved, #regPending, #regRejected")
    .forEach((el) => {
      el.innerHTML = '<div class="skeleton-text w-50"></div>';
    });
  ["regConversionValue", "regRejectionValue", "regApprovalTimeValue"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="skeleton-text w-50 d-inline-block"></div>';
  });

  // Show skeleton for governorate table
  const tbody = document.getElementById("governorateTableBody");
  if (tbody) {
    const makeSkeletonRow = () => `
            <tr class="skeleton-row">
                <td><div class="skeleton-text w-75"></div></td>
                ${'<td><div class="skeleton-text w-50 mx-auto"></div></td>'.repeat(4)}
                <td><div class="skeleton-text w-75 mx-auto"></div></td>
            </tr>
        `;
    tbody.innerHTML = makeSkeletonRow().repeat(3);
  }

  // Show skeleton for risk radar
  const riskList = document.getElementById("riskList");
  if (riskList) {
    riskList.innerHTML = `
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
            <li class="list-group-item d-flex justify-content-between align-items-center skeleton-row">
                <div><div class="skeleton-text w-75 mb-1"></div><div class="skeleton-text w-50"></div></div>
                <div class="skeleton-text w-25"></div>
            </li>
        `;
  }

  // Show skeleton for comparative analysis
  const _topPerformersList = document.getElementById("topPerformersList");
  if (_topPerformersList) _topPerformersList.innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;
  const _lowPerformersList = document.getElementById("lowPerformersList");
  if (_lowPerformersList) _lowPerformersList.innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;

  // Skeleton for registration table
  const regTbody = document.getElementById("registrationTableBody");
  if (regTbody) {
    regTbody.innerHTML = Array(3).fill(`
      <tr>
        <td><div class="skeleton-text w-75"></div></td>
        <td><div class="skeleton-text w-50"></div></td>
        <td><div class="skeleton-text w-75"></div></td>
        <td><div class="skeleton-text w-50"></div></td>
        <td><div class="skeleton-text w-50 mx-auto"></div></td>
        <td><div class="skeleton-text w-50"></div></td>
        <td><div class="skeleton-text w-50 mx-auto"></div></td>
        <td><div class="skeleton-text w-50 mx-auto"></div></td>
        <td><div class="skeleton-text w-25 mx-auto"></div></td>
      </tr>
    `).join("");
  }

  // Clear charts if they exist
  if (trendChartInstance) trendChartInstance.destroy();
  if (governanceChart) governanceChart.destroy();
  if (funnelChartInstance) { funnelChartInstance.destroy(); funnelChartInstance = null; }
  if (sourceChartInstance) { sourceChartInstance.destroy(); sourceChartInstance = null; }
}

function hideSkeletonLoaders() {
  // Clear KPI card skeletons that weren't filled by updateNetworkSummary
  document
    .querySelectorAll("#totalKg, #totalChildren, #avgAttendance, #incidentRate, #enrollmentRate")
    .forEach((el) => {
      if (el.querySelector(".skeleton-text")) el.textContent = "--";
    });
  // Clear registration KPI skeletons
  document
    .querySelectorAll("#regTotalApplications, #regNewApplications, #regApproved, #regPending, #regRejected")
    .forEach((el) => {
      if (el.querySelector(".skeleton-text")) el.textContent = "--";
    });
  // Clear loading spinners in containers that were never populated
  document.querySelectorAll(".spinner-border").forEach((spinner) => {
    const container = spinner.closest("[aria-live]");
    if (container && container.querySelectorAll(".skeleton-row, .spinner-border").length) {
      container.innerHTML = `<p class="text-muted text-center small py-2">${adminAnalyticsText("لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data")}</p>`;
    }
  });
}

function updateLastUpdatedTimestamp() {
  const el = document.getElementById("analyticsLastUpdated");
  if (!el) return;
  const now = new Date();
  const formatter = new Intl.DateTimeFormat(adminAnalyticsLocale(), {
    dateStyle: "medium",
    timeStyle: "short",
  });
  el.innerHTML = `<i class="bi bi-clock"></i> <span>${adminAnalyticsText("آخر تحديث:", "Last updated:")} ${formatter.format(now)}</span>`;

  // Update date range badge with unambiguous DD MMM YYYY display
  const start = document.getElementById("periodStart")?.value;
  const end   = document.getElementById("periodEnd")?.value;
  const badge = document.getElementById("dateRangeBadge");
  if (badge && start && end) {
    const fmt = new Intl.DateTimeFormat(adminAnalyticsLocale(), { day: "2-digit", month: "short", year: "numeric" });
    const fmtDate = (s) => fmt.format(new Date(s + "T00:00:00"));
    badge.textContent = `${fmtDate(start)} – ${fmtDate(end)}`;
    badge.classList.remove("d-none");
  }
}

function updateNetworkSummary(summary) {
   if (!summary) {
     return;
   }

   // Update KPI cards with proper formatting
   safeSetText(
     "totalKg",
     summary.total_kindergartens?.toLocaleString(adminAnalyticsLocale()) || "0"
   );

   const childrenCount = summary.total_children || 0;
   safeSetText("totalChildren", childrenCount.toLocaleString(adminAnalyticsLocale()));

   const attendanceRate = summary.attendance_rate || 0;
   safeSetText("avgAttendance", attendanceRate.toFixed(1) + "%");

   const incidentRate = summary.incident_rate || 0;
   safeSetText("incidentRate", incidentRate.toFixed(2) + "/1K");

   const enrollmentRate = summary.enrollment_rate || 0;
   safeSetText("enrollmentRate", enrollmentRate.toFixed(1) + "%");

   // Update progress bars
   const enrollmentBar = document.getElementById("enrollmentRateBar");
   if (enrollmentBar) {
     enrollmentBar.style.width = Math.min(enrollmentRate, 100) + "%";
     enrollmentBar.className = `progress-bar ${enrollmentRate > 90 ? "bg-success" : enrollmentRate > 70 ? "bg-info" : "bg-warning"}`;
   }

   // Add visual score indicators to KPI cards
   const kgCard = document.querySelector('[aria-label*="Facilities"]');
   if (kgCard) {
     kgCard.classList.add("kpi-card-v2--success", "kpi-score-good");
   }

   updateTrendIndicators(summary);
   if (lastDashboardData) {
     lastDashboardData.network_summary = summary;
     renderSparklines(lastDashboardData);
   }

   // Populate Overview operational health summary cards
   const ohAtt = document.getElementById("ohAttendanceHealth");
   if (ohAtt) {
     const rate = (summary.attendance_rate || 0).toFixed(1);
     const cls = attendanceRate >= 80 ? "text-success" : attendanceRate >= 60 ? "text-warning" : "text-danger";
     ohAtt.textContent = rate + "%";
     ohAtt.className = `fw-bold fs-5 ${cls}`;
   }

   const ohGov = document.getElementById("ohGovernanceScore");
   if (ohGov) {
     const govVal = summary.governance_avg_score || 0;
     ohGov.textContent = govVal.toFixed(1);
     // v2 card — no Bootstrap class needed, value only
     ohGov.removeAttribute('class');
     // Add score tier class for visual indication
     ohGov.classList.add(govVal >= 80 ? "text-success" : govVal >= 60 ? "text-warning" : "text-danger");
   }
   // Update data quality ring if already loaded
   if (typeof window._updateDQRing === 'function' && summary.data_quality_score != null) {
     window._updateDQRing(summary.data_quality_score);
   }
 }

function updateTrendIndicators(summary) {
  renderDeltaIndicator(
    summary?.deltas?.attendance_rate,
    "attendanceTrendIndicator",
    "attendance_rate"
  );
  renderDeltaIndicator(summary?.deltas?.incident_rate, "incidentTrend", "incident_rate");
  renderDeltaIndicator(summary?.deltas?.total_kindergartens, "kpiKgGrowth", "total_kindergartens");
}

function renderDeltaIndicator(delta, elementId, metricKey) {
  const element = document.getElementById(elementId);
  if (!element) return;

  const unavailableText = t("timeframes", "vsPrevious").startsWith("vs")
    ? "No previous-period data"
    : "غير متوفر للفترة السابقة";

  if (!delta || delta.source !== "real" || delta.delta_percent == null) {
    element.className = "text-muted";
    element.innerHTML = `<i class="bi bi-dash me-1"></i>${unavailableText}`;
    return;
  }

  const percent = Math.abs(Number(delta.delta_percent || 0)).toFixed(1);
  const direction = delta.direction || "neutral";
  const isNeutral = direction === "neutral";
  const isImprovement =
    direction === "up" ||
    (metricKey === "incident_rate" && direction === "down");
  const icon = isNeutral
    ? "bi-dash"
    : isImprovement
      ? "bi-arrow-up-short"
      : "bi-arrow-down-short";
  const className = isNeutral ? "kpi-delta kpi-delta--flat" : isImprovement ? "kpi-delta kpi-delta--up" : "kpi-delta kpi-delta--down";
  const label = t("timeframes", "vsPrevious");
  const ariaLabel = isNeutral
    ? t("timeframes", "noChange")
    : isImprovement
      ? `${t("timeframes", "improved")} ${percent}% ${t("timeframes", "vsPrevious")}`
      : `${t("timeframes", "declined")} ${percent}% ${t("timeframes", "vsPrevious")}`;

  // For incidents, down is good (fewer incidents)
  // For other metrics, up is good (more facilities, more attendance, etc.)
  const displaySign = isNeutral ? "" : (isImprovement ? "▲" : "▼");

  element.className = className;
  element.setAttribute("aria-label", ariaLabel);
  element.innerHTML = `<i class="bi ${icon}" aria-hidden="true"></i><span class="delta-value" aria-hidden="true">${displaySign}${percent}%</span><span class="delta-label">${label}</span>`;
}

function applyComparison() {
  const type = document.getElementById('comparisonType').value;
  const periodStart = document.getElementById('periodStart').value;
  const periodEnd = document.getElementById('periodEnd').value;

  let compareStart, compareEnd;

  if (type === 'previous') {
    const start = new Date(periodStart);
    const end = new Date(periodEnd);
    const duration = (end - start) / (1000 * 60 * 60 * 24);

    compareEnd = new Date(start);
    compareEnd.setDate(compareEnd.getDate() - 1);
    compareStart = new Date(compareEnd);
    compareStart.setDate(compareStart.getDate() - duration);
  } else {
    compareStart = document.getElementById('compareStart').value;
    compareEnd = document.getElementById('compareEnd').value;
  }

  if (!compareStart || !compareEnd) {
    alert(adminAnalyticsText('يرجى تحديد نطاق المقارنة', 'Please select comparison range'));
    return;
  }

  fetchComparison(periodStart, periodEnd, compareStart, compareEnd);

  if (window.bootstrap && bootstrap.Modal) {
    bootstrap.Modal.getInstance(document.getElementById('comparePeriodModal'))?.hide();
  }
}

async function fetchComparison(periodStart, periodEnd, compareStart, compareEnd) {
  const governorate = document.getElementById('governorateFilter')?.value;

  const params = new URLSearchParams({
    mode: 'period',
    period_start: periodStart,
    period_end: periodEnd,
    compare_start: compareStart,
    compare_end: compareEnd
  });
  if (governorate) params.append('governorate', governorate);

  try {
    const response = await fetchWithAuth(`/api/analytics/compare?${params}`);
    if (!response.ok) throw new Error('Comparison failed');

    const data = await response.json();
    renderComparisonDeltas(data.deltas);
  } catch (error) {
    console.error('Comparison error:', error);
    showToast(
      adminAnalyticsText('فشلت المقارنة', 'Comparison failed'),
      'error'
    );
  }
}

function renderComparisonDeltas(deltas) {
  const kpiMappings = {
    'totalKg': deltas.total_kindergartens,
    'totalChildren': deltas.total_children,
    'avgAttendance': deltas.attendance_rate,
    'incidentRate': deltas.incident_rate,
    'ohGovernanceScore': deltas.governance_avg_score
  };

  Object.entries(kpiMappings).forEach(([kpiId, delta]) => {
    const valueEl = document.getElementById(kpiId);
    if (!valueEl) return;

    const card = valueEl.closest('.kpi-card-v2');
    if (!card) return;

    const footer = card.querySelector('.kpi-card-v2__footer');
    if (!footer) return;

    let deltaEl = footer.querySelector('.kpi-delta.comparison-delta');
    if (!deltaEl) {
      deltaEl = document.createElement('span');
      deltaEl.className = 'kpi-delta comparison-delta';
      footer.appendChild(deltaEl);
    }

    const direction = delta.direction;
    const significant = delta.significant;
    const absPct = Math.abs(delta.percentage).toFixed(1);

    let icon, colorClass, bgClass;
    if (direction === 'up') {
      icon = 'bi-arrow-up';
      colorClass = 'text-success';
      bgClass = 'kpi-delta--up';
    } else if (direction === 'down') {
      icon = 'bi-arrow-down';
      colorClass = 'text-danger';
      bgClass = 'kpi-delta--down';
    } else {
      icon = 'bi-dash';
      colorClass = 'text-muted';
      bgClass = 'kpi-delta--flat';
    }

    deltaEl.className = `kpi-delta ${bgClass} comparison-delta`;
    deltaEl.innerHTML = `<i class="bi ${icon} me-1" aria-hidden="true"></i>${absPct}%${significant ? '<span class="badge bg-light text-dark ms-1" style="font-size:0.625rem;padding:0.25em 0.5em">SIG</span>' : ''}`;
    deltaEl.setAttribute('aria-label', `${absPct}% ${direction}${significant ? ' significant' : ''}`);
  });
}

document.getElementById('comparisonType')?.addEventListener('change', function() {
  const customFields = document.getElementById('customRangeFields');
  if (this.value === 'custom') {
    customFields.classList.remove('d-none');
  } else {
    customFields.classList.add('d-none');
  }
});

function updateTrendCharts(attendanceData, incidentData) {
  const ctx = document.getElementById("trendChart");
  if (!ctx) return;

  // Show loading overlay, hide error
  const overlay = document.getElementById("trendChartOverlay");
  const errorDiv = document.getElementById("trendChartError");
  if (overlay) overlay.classList.remove("d-none");
  if (errorDiv) {
    errorDiv.classList.remove("show");
    errorDiv.classList.add("hidden");
  }

  if (!adminAnalyticsHasChart()) {
    if (overlay) overlay.classList.add("d-none");
    if (errorDiv) {
      errorDiv.classList.add("show");
      errorDiv.classList.remove("hidden");
      const message = errorDiv.querySelector("p");
      if (message) {
        message.textContent = adminAnalyticsText(
          "تعذر تحميل مكتبة الرسوم البيانية.",
          "Chart library could not be loaded."
        );
      }
    }
    return;
  }

  if (trendChartInstance) {
    trendChartInstance.destroy();
  }

  window.__trendData = {
    attendance: attendanceData || [],
    incidents: incidentData || [],
  };

  const chartData = buildTrendChartData("attendance");

  trendChartInstance = new Chart(ctx, {
    type: "line",
    data: chartData.data,
    options: chartData.options,
  });

  // Setup radio button event listeners
  setupTrendControls(attendanceData, incidentData);

  // Hide loading overlay
  setTimeout(() => {
    if (overlay) overlay.classList.add("d-none");
  }, 500);
}

function setupTrendControls(_attendanceData, _incidentData) {
  const attendanceRadio = document.getElementById("attendanceTrend");
  const incidentsRadio = document.getElementById("incidentsTrend");

  if (attendanceRadio && incidentsRadio && !attendanceRadio.dataset.analyticsBound) {
    attendanceRadio.dataset.analyticsBound = "true";
    incidentsRadio.dataset.analyticsBound = "true";
    attendanceRadio.addEventListener("change", () => {
      if (attendanceRadio.checked) {
        updateTrendChart("attendance");
      }
    });

    incidentsRadio.addEventListener("change", () => {
      if (incidentsRadio.checked) {
        updateTrendChart("incidents");
      }
    });
  }
}

function updateTrendChart(type) {
  if (!trendChartInstance) return;
  const chartData = buildTrendChartData(type);
  trendChartInstance.data = chartData.data;
  trendChartInstance.options = chartData.options;
  trendChartInstance.update("active");
  // Keep annotations aligned when the displayed metric changes.
  if (chartAnnotations && chartAnnotations.length) {
    renderTrendChartWithAnnotations();
  }
}

function buildTrendChartData(type) {
  const dataSeries = window.__trendData?.[type] || [];
  const forecastPayload = window.__forecastData || {};
  const forecastSeries = forecastPayload[type === "attendance" ? "attendance" : "incidents"] || {};
  const forecastPoints = forecastSeries.forecast_points || [];
  const confidence = forecastSeries.confidence || { lower: [], upper: [] };

  const labels = dataSeries.map((d) => formatDateForDisplay(d.date));
  const forecastLabels = forecastPoints.map((d) => formatDateForDisplay(d.date));
  const fullLabels = labels.concat(forecastLabels);

  // new Array(n) throws RangeError for negative n — dataSeries.length - 1 is
  // -1 whenever there's no attendance/incident data for the selected range
  // (a real, reachable case, not just a test artifact), which previously
  // crashed here and silently aborted every widget load still queued after
  // updateTrendCharts() in loadAdminAnalytics's shared try block (alerts,
  // data quality, targets, benchmarks, recommendations, registration
  // analytics, and the risk-radar/executive-banner event never ran).
  const paddingLength = Math.max(0, dataSeries.length - 1);

  const lineColor = type === "attendance" ? "#2563EB" : "#DC2626";
  const lineLabel =
    type === "attendance"
      ? adminAnalyticsText("معدل الحضور", "Attendance Rate")
      : adminAnalyticsText("عدد الحوادث", "Incident Rate");

  return {
    data: {
      labels: fullLabels,
      datasets: [
        {
          label: lineLabel,
          data: safeChartData(dataSeries.map((d) => d.value)),
          borderColor: lineColor,
          backgroundColor: function(context) {
            const chart = context.chart;
            const { ctx: c, chartArea } = chart;
            if (!chartArea) return 'transparent';
            const gradient = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
            const alpha = type === "attendance" ? "0.18" : "0.15";
            gradient.addColorStop(0, lineColor.replace(')', ', ' + alpha + ')').replace('rgb', 'rgba'));
            gradient.addColorStop(1, 'rgba(255,255,255,0)');
            return gradient;
          },
          yAxisID: "y",
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 7,
          pointBackgroundColor: "#fff",
          pointBorderColor: lineColor,
          pointBorderWidth: 2,
        },
        {
          label: adminAnalyticsText("توقعات", "Forecast"),
          data: new Array(paddingLength)
            .fill(null)
            .concat(forecastPoints.map((d) => d.value)),
          borderColor: "#0EA5E9",
          borderDash: [6, 4],
          fill: false,
          pointRadius: 2,
        },
        {
          label: adminAnalyticsText("حد أدنى", "Lower bound"),
          data: new Array(paddingLength)
            .fill(null)
            .concat((confidence.lower || []).map((d) => d.value)),
          borderColor: "rgba(31,94,71,0.2)",
          backgroundColor: "rgba(31,94,71,0.1)",
          fill: "+1",
          pointRadius: 0,
        },
        {
          label: adminAnalyticsText("حد أعلى", "Upper bound"),
          data: new Array(paddingLength)
            .fill(null)
            .concat((confidence.upper || []).map((d) => d.value)),
          borderColor: "rgba(31,94,71,0.2)",
          backgroundColor: "rgba(31,94,71,0.1)",
          fill: false,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: "index",
        intersect: false,
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            usePointStyle: true,
            padding: 20,
            font: {
              size: 12,
              weight: "bold",
              family: adminAnalyticsText("Cairo, sans-serif", "Inter, sans-serif"),
            },
          },
        },
        tooltip: {
          mode: "index",
          intersect: false,
          backgroundColor: "rgba(15,23,42,0.92)",
          titleColor: "#F8FAFC",
          bodyColor: "#CBD5E1",
          padding: 12,
          cornerRadius: 10,
          boxPadding: 4,
          bodyColor: "#fff",
          borderColor: lineColor,
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: true,
          callbacks: {
            title: function (context) {
              return `${adminAnalyticsText("تاريخ", "Date")}: ${context[0].label}`;
            },
            label: function (context) {
              return (
                context.dataset.label +
                ": " +
                context.parsed.y.toLocaleString(adminAnalyticsLocale())
              );
            },
          },
        },
      },
      scales: {
        y: {
          type: "linear",
          display: true,
          position: "left",
          beginAtZero: true,
          title: {
            display: true,
            text: lineLabel,
            font: {
              size: 14,
              weight: "bold",
              family: adminAnalyticsText("Cairo, sans-serif", "Inter, sans-serif"),
            },
          },
          grid: {
            color: "rgba(0,0,0,0.05)",
          },
          ticks: {
            callback: function (value) {
              return value.toLocaleString(adminAnalyticsLocale());
            },
          },
        },
        x: {
          title: {
            display: true,
            text: adminAnalyticsText("التاريخ", "Date"),
            font: {
              size: 14,
              weight: "bold",
            },
          },
          grid: {
            display: false,
          },
        },
      },
      elements: {
        point: {
          hoverBorderWidth: 3,
        },
      },
    },
  };
}

// =============================================================================
// Chart Annotations — holidays, anomalies, and significant events overlayed
// on the trend chart via the Chart.js annotation plugin.
// =============================================================================
async function loadChartAnnotations() {
  const periodStart = document.getElementById('periodStart')?.value;
  const periodEnd = document.getElementById('periodEnd')?.value;

  if (!periodStart || !periodEnd) return;

  try {
    const params = new URLSearchParams({
      period_start: periodStart,
      period_end: periodEnd,
    });
    const gov = document.getElementById('governorateFilter')?.value;
    if (gov) params.set('governorate', gov);

    const response = await fetchWithAuth(`/api/analytics/annotations?${params}`);
    if (!response.ok) throw new Error('Failed to load annotations');

    const data = await response.json();
    chartAnnotations = data.annotations || [];

    // Re-render the trend chart with the loaded annotations.
    if (trendChartInstance) {
      renderTrendChartWithAnnotations();
    }
  } catch (error) {
    console.error('Error loading annotations:', error);
  }
}

function _currentTrendMetric() {
  const incidentsRadio = document.getElementById('incidentsTrend');
  if (incidentsRadio && incidentsRadio.checked) return 'incidents';
  return 'attendance';
}

// Map an ISO (YYYY-MM-DD) annotation date to the chart's category label so
// category-axis annotations line up with the plotted data point. Falls back to
// the nearest plotted point when no exact match exists.
function _annotationLabelForDate(isoDate) {
  if (!trendChartInstance) return isoDate;
  const series = window.__trendData?.attendance || [];
  const labels = trendChartInstance.data.labels || [];
  for (let i = 0; i < series.length; i++) {
    if (series[i] && series[i].date === isoDate && labels[i]) {
      return labels[i];
    }
  }
  const target = new Date(isoDate).getTime();
  let bestIdx = -1;
  let bestDiff = Infinity;
  for (let i = 0; i < series.length; i++) {
    if (!series[i] || !series[i].date) continue;
    const diff = Math.abs(new Date(series[i].date).getTime() - target);
    if (diff < bestDiff) {
      bestDiff = diff;
      bestIdx = i;
    }
  }
  return bestIdx >= 0 && labels[bestIdx] ? labels[bestIdx] : isoDate;
}

function renderTrendChartWithAnnotations() {
  if (!trendChartInstance || !chartAnnotations) return;

  const chart = trendChartInstance;
  const lang = adminAnalyticsText('ar', 'en');

  const holidays = chartAnnotations.filter(a => a.type === 'holiday');
  const anomalies = chartAnnotations.filter(a => a.type === 'anomaly');
  const currentMetric = _currentTrendMetric();

  const annotationConfig = { annotations: {} };

  // Vertical dashed lines for holidays/events.
  holidays.forEach((holiday, idx) => {
    const label = lang === 'en' ? holiday.label_en : holiday.label_ar;
    annotationConfig.annotations[`holiday_${idx}`] = {
      type: 'line',
      xMin: _annotationLabelForDate(holiday.date),
      xMax: _annotationLabelForDate(holiday.date),
      borderColor: holiday.color,
      borderWidth: 2,
      borderDash: [5, 5],
      label: {
        content: label,
        enabled: true,
        position: 'start',
        backgroundColor: 'rgba(245, 158, 11, 0.85)',
        color: 'white',
        font: { size: 10 }
      }
    };
  });

  // Highlight anomaly points with a colored box + marker.
  anomalies.forEach((anomaly, idx) => {
    const xLabel = _annotationLabelForDate(anomaly.date);
    annotationConfig.annotations[`anomaly_${idx}`] = {
      type: 'box',
      xMin: xLabel,
      xMax: xLabel,
      backgroundColor: (anomaly.color || '#ef4444') + '20',
      borderColor: anomaly.color || '#ef4444',
      borderWidth: 1
    };

    // Only draw the point marker when the anomaly belongs to the metric
    // currently shown on the trend chart.
    if (!anomaly.metric || anomaly.metric === currentMetric) {
      annotationConfig.annotations[`anomaly_point_${idx}`] = {
        type: 'point',
        xValue: xLabel,
        yValue: getAnomalyYValue(anomaly),
        radius: 6,
        backgroundColor: anomaly.color || '#ef4444',
        borderColor: 'white',
        borderWidth: 2
      };
    }
  });

  chart.options.plugins.annotation = annotationConfig;
  chart.update();
}

function getAnomalyYValue(anomaly) {
  if (!trendChartInstance) return 0;
  const chart = trendChartInstance;
  const dataset = chart.data.datasets[0];
  if (!dataset || !dataset.data) return 0;

  const series = window.__trendData?.[_currentTrendMetric()] || [];
  for (let i = 0; i < series.length; i++) {
    if (series[i] && series[i].date === anomaly.date) {
      const v = dataset.data[i];
      return (v && typeof v === 'object') ? v.y : (Number.isFinite(v) ? v : 0);
    }
  }
  return 0;
}

function formatDateForDisplay(dateStr) {
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString(adminAnalyticsLocale(), {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch (e) {
    return dateStr;
  }
}

function updateRiskRadar(riskData) {
  const list = document.getElementById("riskList");
  const container = document.getElementById("riskListContainer");
  const noData = document.getElementById("noRiskData");

  if (!list || !container || !noData) return;

  // Clear existing content
  list.innerHTML = "";

  // Validate risk items - filter out invalid/placeholder items
  if (!riskData || riskData.length === 0) {
    container.classList.add("d-none");
    noData.classList.remove("d-none");
    return;
  }

  // get_high_risk_children() returns {child_id, kindergarten_id, child_name,
  // kindergarten_name, risk_type, risk_value, description} — not the
  // {name, kindergarten, reason, risk_score} shape this filter used to
  // check, which discarded every real entry and always fell through to the
  // "no risk data" empty state regardless of actual risk data.
  const validRiskItems = riskData.filter(function (item) {
    if (!item) return false;
    const name = typeof item.child_name === "string" ? item.child_name.trim() : "";
    const kindergarten = typeof item.kindergarten_name === "string" ? item.kindergarten_name.trim() : "";
    const reason = typeof item.description === "string" ? item.description.trim() : "";
    const placeholderValues = new Set([
      "غير محدد",
      "غير متاح",
      "سبب غير محدد",
      "Not specified",
      "Unavailable",
      "Unspecified reason",
      "Unknown",
    ]);
    const hasValidName = name.length > 0 && !placeholderValues.has(name);
    const hasValidKindergarten = kindergarten.length > 0 && !placeholderValues.has(kindergarten);
    const hasValidScore = Number.isFinite(Number(item.risk_value)) && item.risk_value >= 0;
    const hasValidReason = reason.length > 0 && !placeholderValues.has(reason);
    const noCorruptedText = window.KpiValidation
      ? !window.KpiValidation.containsCorruptedArabic(item.child_name) &&
        !window.KpiValidation.containsCorruptedArabic(item.kindergarten_name) &&
        !window.KpiValidation.containsCorruptedArabic(item.description)
      : true;
    const isNotPlaceholder = hasValidName && hasValidKindergarten && hasValidScore && hasValidReason && noCorruptedText;
    return isNotPlaceholder;
  });

  if (validRiskItems.length === 0) {
    container.classList.add("d-none");
    noData.classList.remove("d-none");
    return;
  }

  // Show risk data
  container.classList.remove("d-none");
  noData.classList.add("d-none");

  // Sort by risk severity descending (see window._classifyRisk — risk_value's
  // scale/direction depends on risk_type, so rank by classified severity
  // tier first, then by raw risk_value within a tier).
  const severityRank = { critical: 3, high: 2, medium: 1 };
  validRiskItems.sort(function (a, b) {
    const rankA = window._classifyRisk ? severityRank[window._classifyRisk(a)] : 0;
    const rankB = window._classifyRisk ? severityRank[window._classifyRisk(b)] : 0;
    if (rankA !== rankB) return rankB - rankA;
    return (b.risk_value || 0) - (a.risk_value || 0);
  });

  // Use v2 renderer if available, otherwise fall back to legacy
  if (typeof window._renderRiskCards === 'function') {
    window._renderRiskCards(validRiskItems);
    return;
  }

  validRiskItems.forEach(function (item) {
    const li = document.createElement("li");
    li.className = "list-group-item d-flex justify-content-between align-items-center border-0 py-3";
    const riskScore = item.risk_value || 0;
    const riskColor = riskScore >= 70 ? "danger" : riskScore >= 40 ? "warning" : "success";
    const safeName = item.child_name || "غير متاح";
    const safeKindergarten = item.kindergarten_name || "غير محدد";
    const safeReason = item.description || "سبب غير محدد";
    li.innerHTML = `<div class="flex-grow-1">
      <div class="d-flex align-items-center mb-1">
        <span class="fw-bold text-dark me-2">${adminAnalyticsLiteral(safeName)}</span>
        <small class="badge bg-${riskColor} text-white">${riskScore} ${adminAnalyticsText("خطر", "risk")}</small>
      </div>
      <small class="text-muted d-block">${adminAnalyticsLiteral(safeKindergarten)}</small>
      <div class="small text-danger mt-1">${adminAnalyticsLiteral(safeReason)}</div>
    </div>`;
    li.style.cursor = "pointer";
    li.addEventListener("click", function () {
      if (item.kindergarten_id) window.location.href = `/admin/analytics/drilldown/KINDERGARTEN/${item.kindergarten_id}`;
    });
    list.appendChild(li);
  });
}

function updateGovernorateBreakdown(breakdownData) {
   const table = document.getElementById("governorateTable");
   const tbody = document.getElementById("governorateTableBody");
   if (!tbody || !table) return;

   tbody.innerHTML = "";

   const rows = (breakdownData || []).filter(function (row) {
     if (!row || typeof row.governorate !== "string" || !row.governorate.trim()) return false;
     if (window.KpiValidation && window.KpiValidation.containsCorruptedArabic(row.governorate)) return false;
     return true;
   });

   if (rows.length === 0) {
     tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">${adminAnalyticsText("لا توجد بيانات للفترة المحددة", "No data for the selected period")}</td></tr>`;
     if (governorateTableSorter) {
       governorateTableSorter.destroy();
       governorateTableSorter = null;
     }
     return;
   }

   let green = 0, amber = 0, red = 0;

   rows.forEach(function (row) {
     const tr = document.createElement("tr");
     tr.setAttribute("data-gov-id", row.governorate);
     tr.style.cursor = "pointer";
     tr.title = adminAnalyticsText(
       `انقر لعرض تفاصيل محافظة ${row.governorate}`,
       `Click to view details for governorate ${row.governorate}`
     );
     tr.addEventListener("click", function () {
       window.location.href = `/admin/analytics/drilldown/GOVERNORATE/${row.governorate}`;
     });

     // Validate and format values
     const govScore = Number(row.governance_score);
     const govScoreValid = Number.isFinite(govScore) && govScore >= 0 && govScore <= 100;
     const displayScore = govScoreValid ? govScore.toFixed(1) : "--";
     const scorePercent = govScoreValid ? govScore : 0;

     tr.innerHTML = `
             <td class="fw-bold">${adminAnalyticsLiteral(row.governorate)}</td>
             <td class="text-center">${row.kindergarten_count}</td>
             <td class="text-center">${row.children_count}</td>
             <td class="text-center" data-sort="${row.attendance_rate}">
                 <span class="badge ${row.attendance_rate >= 85 ? "bg-success-subtle text-success-emphasis" : "bg-warning-subtle text-warning-emphasis"}">
                     ${(row.attendance_rate ?? 0).toFixed(1)}%
                 </span>
             </td>
             <td class="text-center" data-sort="${row.incident_rate}">${(row.incident_rate ?? 0).toFixed(2)}/1K</td>
             <td class="text-center" data-sort="${govScore}">
                 <div class="d-flex align-items-center justify-content-center">
                     <span class="fw-bold me-2">${displayScore}</span>
                     <div class="progress" style="width: 50px; height: 4px;" role="progressbar" aria-valuenow="${govScoreValid ? govScore : 0}" aria-valuemin="0" aria-valuemax="100">
                         <div class="progress-bar ${govScoreValid ? getScoreColor(govScore) : "bg-secondary"}" style="width: ${scorePercent}%"></div>
                     </div>
                 </div>
             </td>
         `;
     tbody.appendChild(tr);

     // Use the same classification as KPI service (>=80 Green, >=60 Amber, else Red)
     if (govScoreValid) {
       if (govScore >= 80) green++;
       else if (govScore >= 60) amber++;
       else red++;
     }
   });

   updateGovernanceChart(green, amber, red);
   updateRiskHeatmap(rows);

   // Initialize or refresh sorter
   if (typeof window.Tablesort !== "function") {
     return;
   }
   if (governorateTableSorter) {
     governorateTableSorter.refresh();
   } else {
     governorateTableSorter = new window.Tablesort(table);
   }
 }

function updateRiskHeatmap(breakdownData) {
  const container = document.getElementById("riskHeatmap");
  if (!container) return;
  container.innerHTML = "";
  const rows = (breakdownData || []).filter(function (row) {
    return row && typeof row.governorate === "string" && row.governorate.trim();
  });
  if (!rows.length) {
    container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsNoDataText()}</div>`;
    return;
  }

  // Highest-risk (lowest score) governorates surface first.
  const sorted = rows.slice().sort((a, b) => {
    const scoreA = Number.isFinite(Number(a.governance_score)) ? Number(a.governance_score) : 0;
    const scoreB = Number.isFinite(Number(b.governance_score)) ? Number(b.governance_score) : 0;
    return scoreA - scoreB;
  });

  const list = document.createElement("ul");
  list.className = "row g-2 list-unstyled mb-0";
  list.setAttribute("role", "list");

  sorted.slice(0, 12).forEach((row) => {
    const score = Number.isFinite(Number(row.governance_score)) ? Number(row.governance_score) : 0;
    const level =
      score >= 80
        ? { color: "bg-success", label: adminAnalyticsText("منخفضة", "Low risk") }
        : score >= 60
        ? { color: "bg-warning", label: adminAnalyticsText("متوسطة", "Moderate risk") }
        : { color: "bg-danger", label: adminAnalyticsText("مرتفعة", "High risk") };

    const item = document.createElement("li");
    item.className = "col-6 col-md-4 col-lg-3";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `risk-cell text-white ${level.color}`;
    btn.setAttribute(
      "aria-label",
      adminAnalyticsText(
        `${row.governorate}: ${level.label}، ${score.toFixed(1)}٪. عرض التفاصيل`,
        `${row.governorate}: ${level.label}, ${score.toFixed(1)}%. View details`
      )
    );
    btn.innerHTML = `
      <span class="risk-cell__name">${adminAnalyticsLiteral(row.governorate)}</span>
      <span class="risk-cell__score">${score.toFixed(1)}%</span>
    `;
    btn.addEventListener("click", () => {
      window.location.href = `/admin/analytics/drilldown/GOVERNORATE/${row.governorate}`;
    });

    item.appendChild(btn);
    list.appendChild(item);
  });

  container.appendChild(list);
}

async function loadComparativeAnalysis(start, end) {
   const topList = document.getElementById("topPerformersList");
   const lowList = document.getElementById("lowPerformersList");
   if (!topList || !lowList) return;

   topList.innerHTML = `<div class="list-group-item text-center text-muted small">${adminAnalyticsText("جارٍ تحميل البيانات، يرجى الانتظار.", "Loading...")}</div>`;
   lowList.innerHTML = `<div class="list-group-item text-center text-muted small">${adminAnalyticsText("جارٍ تحميل البيانات، يرجى الانتظار.", "Loading...")}</div>`;

   try {
     const gov = document.getElementById("governorateFilter")?.value || "";
     const govParam = gov ? `&governorate=${encodeURIComponent(gov)}` : "";
     const [topResponse, lowResponse] = await Promise.all([
       fetchWithAuth(
         `/api/analytics/rankings/governance_score?top_n=5&period_start=${start}&period_end=${end}${govParam}`
       ),
       fetchWithAuth(
         `/api/analytics/rankings/governance_score?top_n=5&bottom=true&period_start=${start}&period_end=${end}${govParam}`
       ),
     ]);

     if (!topResponse || !lowResponse) return;

     const topData = await topResponse.json();
     const lowData = await lowResponse.json();

     // Track seen kindergarten IDs to prevent duplicates across lists
     const seenTopIds = new Set((topData.rankings || []).map(function (r) { return r.kindergarten_id; }));
     const topCount = (topData.rankings || []).length;
     const lowCount = (lowData.rankings || []).length;

     renderRankingList(topList, topData.rankings, "top", seenTopIds);
     renderRankingList(lowList, lowData.rankings, "low", seenTopIds, topCount);

     // Governance tab hosts its own copy of the leaderboard under distinct IDs
     const govTopList = document.getElementById("govTopPerformersList");
     const govLowList = document.getElementById("govLowPerformersList");
     if (govTopList) renderRankingList(govTopList, topData.rankings, "top", seenTopIds);
     if (govLowList) renderRankingList(govLowList, lowData.rankings, "low", seenTopIds, topCount);
   } catch (error) {
     console.error("Comparative analysis error:", error);
     const failHtml = `<div class="list-group-item text-danger small">${adminAnalyticsText("تعذر تحميل التصنيفات.", "Unable to load rankings.")}</div>`;
     topList.innerHTML = failHtml;
     lowList.innerHTML = failHtml;
     const govTopList = document.getElementById("govTopPerformersList");
     const govLowList = document.getElementById("govLowPerformersList");
     if (govTopList) govTopList.innerHTML = failHtml;
     if (govLowList) govLowList.innerHTML = failHtml;
   }
 }

function renderRankingList(element, rankings, type, seenIds, otherListCount) {
   element.innerHTML = "";

   if (!rankings || rankings.length === 0) {
     const emptyItem = document.createElement("div");
     emptyItem.className = "list-group-item text-muted text-center py-4 border-0";
     emptyItem.innerHTML = `
             <i class="bi bi-info-circle fs-2 mb-2 ${type === "top" ? "text-success" : "text-danger"}"></i>
             <div class="small">${adminAnalyticsText("لا توجد بيانات متاحة لهذه الفترة", "No data available for this period")}</div>
         `;
     element.appendChild(emptyItem);
     return;
   }

   // Filter out invalid/corrupted items and items already seen in other list
   const validRankings = rankings.filter(function (item) {
     if (!item) return false;
     if (!item.kindergarten_name || typeof item.kindergarten_name !== "string") return false;
     if (!item.kindergarten_name.trim()) return false;
     // Check for corrupted Arabic text
     if (window.KpiValidation && window.KpiValidation.containsCorruptedArabic(item.kindergarten_name)) return false;
     if (window.KpiValidation && window.KpiValidation.containsCorruptedArabic(item.governorate || "")) return false;
     // For low performers list, filter out items already in top performers
     if (type === "low" && seenIds && seenIds.has(item.kindergarten_id)) return false;
     return true;
   });

   // Show overlap note if both lists have less than 5 items
   const totalAvailable = (otherListCount || 0) + validRankings.length;
   if (totalAvailable < 5) {
     const noteDiv = document.createElement("div");
     noteDiv.className = "list-group-item text-muted small text-center border-0";
     noteDiv.innerHTML = `<i class="bi bi-info-circle me-1"></i>${adminAnalyticsText(
       `ملاحظة: عدد الحضانات المتاحة أقل من 5، لذا قد تظهر نفس الحضانات في أكثر من قائمة.`,
       `Note: Fewer than 5 kindergartens available, so some may appear in both lists.`
     )}`;
     element.appendChild(noteDiv);
   }

   if (validRankings.length === 0) {
     const emptyItem = document.createElement("div");
     emptyItem.className = "list-group-item text-muted text-center py-4 border-0";
     emptyItem.innerHTML = `<i class="bi bi-info-circle fs-2 mb-2 ${type === "top" ? "text-success" : "text-danger"}"></i>
       <div class="small">${adminAnalyticsNoDataText()}</div>`;
     element.appendChild(emptyItem);
     return;
   }

   validRankings.forEach(function (item, index) {
     const div = document.createElement("div");
     div.className = "list-group-item d-flex justify-content-between align-items-center border-0 py-3";

     const rank = index + 1;
     const score = item.value || 0;
     const scoreColor = type === "top" ? "text-success" : "text-danger";
     const rankIcon = type === "top" ? "bi-trophy" : "bi-exclamation-triangle";

     const safeName = window.KpiValidation
       ? window.KpiValidation.sanitizeCorruptedText(item.kindergarten_name, "غير متاح")
       : (item.kindergarten_name || "غير متاح");
     const safeGovernorate = window.KpiValidation
       ? window.KpiValidation.sanitizeCorruptedText(item.governorate, "غير محدد")
       : (item.governorate || "غير محدد");

     div.innerHTML = `
             <div class="d-flex align-items-center flex-grow-1">
                 <div class="rank-circle ${type === "top" ? "bg-success" : "bg-danger"} text-white rounded-circle d-flex align-items-center justify-content-center me-3" style="width: 32px; height: 32px; font-size: 14px; font-weight: bold;">
                     ${rank}
                 </div>
                 <div class="flex-grow-1">
                     <a href="/admin/analytics/drilldown/KINDERGARTEN/${item.kindergarten_id}" class="fw-bold text-dark text-decoration-none d-block" title="${adminAnalyticsText("انقر لعرض تفاصيل الحضانة", "Click to view kindergarten details")}">
                         ${adminAnalyticsLiteral(safeName)}
                     </a>
                     <small class="text-muted d-block">
                         <i class="bi bi-geo-alt me-1"></i>${adminAnalyticsLiteral(safeGovernorate)}
                     </small>
                 </div>
             </div>
             <div class="text-end">
                 <div class="d-flex align-items-center">
                     <span class="badge ${type === "top" ? "bg-success-subtle text-success-emphasis" : "bg-danger-subtle text-danger-emphasis"} rounded-pill me-2 fs-6">
                         ${score.toFixed(1)}
                     </span>
                     <i class="bi ${rankIcon} ${scoreColor}"></i>
                 </div>
             </div>
         `;

     // Add hover effect
     div.addEventListener("mouseenter", function () {
       div.style.backgroundColor = type === "top" ? "rgba(25, 135, 84, 0.05)" : "rgba(220, 53, 69, 0.05)";
     });

     div.addEventListener("mouseleave", function () {
       div.style.backgroundColor = "";
     });

     element.appendChild(div);
   });
 }

function updateGovernanceChart(green, amber, red) {
  const ctx = document.getElementById("governancePieChart");
  if (!ctx) return;

  // Update legend counters
  safeSetText("countGreen", green);
  safeSetText("countAmber", amber);
  safeSetText("countRed", red);
  const total = (green || 0) + (amber || 0) + (red || 0);
  if (total > 0) {
    safeSetText("pctGreen", `${((green / total) * 100).toFixed(0)}%`);
    safeSetText("pctAmber", `${((amber / total) * 100).toFixed(0)}%`);
    safeSetText("pctRed",   `${((red   / total) * 100).toFixed(0)}%`);
  }
  // v2 progress bars
  if (typeof window._updateGovBars === 'function') window._updateGovBars(green, amber, red);

  if (!adminAnalyticsHasChart()) {
    return;
  }

  if (governanceChart) governanceChart.destroy();

  // Calculate average score for center display
  const avgScore = total > 0 ? ((green * 90 + amber * 70 + red * 40) / total / 0.85).toFixed(1) : "0";

  governanceChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: [
        t("statuses", "excellent"),
        t("statuses", "average"),
        t("statuses", "needsImprovement"),
      ],
      datasets: [
        {
          data: safeChartData([green, amber, red]),
          backgroundColor: ["#16A34A", "#D97706", "#DC2626"],
          hoverBackgroundColor: ["#15803D", "#B45309", "#B91C1C"],
          borderWidth: 3,
          borderColor: "#fff",
          hoverOffset: 8,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: {
        duration: 600,
        easing: "easeOutQuart",
        onComplete: function() {
          // Add center label after animation
          const chart = this;
          const ctx = chart.ctx;
          ctx.save();
          ctx.font = "700 1.5rem/" + ctx.canvas.height + "px var(--font-ar)";
          ctx.fillStyle = "var(--slate-900)";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(avgScore, ctx.canvas.width / 2, ctx.canvas.height / 2);
          ctx.restore();
        }
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "rgba(17,24,39,0.92)",
          titleColor: "#f8fafc",
          bodyColor:  "#f8fafc",
          padding:    12,
          cornerRadius: 8,
          displayColors: true,
          callbacks: {
            label: function(ctx) {
              const total = (ctx.dataset.data || []).reduce((a, b) => a + (b || 0), 0);
              const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : "0.0";
              const label = ctx.label || "";
              return `${label}: ${ctx.parsed} (${pct}%)`;
            },
          },
        },
      },
      cutout: "70%",
    },
  });
}

function refreshGovernorateData() {
  const start = document.getElementById("periodStart").value;
  const end = document.getElementById("periodEnd").value;

  if (!start || !end) {
    showToast(
      adminAnalyticsText("يرجى تحديد تاريخ البداية والنهاية", "Please select start and end dates"),
      "warning"
    );
    return;
  }

  // Show loading state
  const tbody = document.getElementById("governorateTableBody");
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary" role="status"></div><span class="ms-2">${adminAnalyticsText("جاري تحديث البيانات...", "Refreshing data...")}</span></td></tr>`;
  }

  // Fetch updated data
  fetchWithAuth(`/api/analytics/governorate-breakdown?period_start=${start}&period_end=${end}`)
    .then((response) => (response ? response.json() : null))
    .then((data) => {
      if (data) {
        updateGovernorateBreakdown(data);
        showToast(
          adminAnalyticsText("تم تحديث بيانات المحافظات", "Governorate data refreshed"),
          "success"
        );
      }
    })
    .catch((error) => {
      console.error("Governorate data refresh error:", error);
      showToast(
        adminAnalyticsText("فشل في تحديث بيانات المحافظات", "Failed to refresh governorate data"),
        "error"
      );
    });
}
window.refreshGovernorateData = refreshGovernorateData;

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = text;
}

function showToast(message, type = "info") {
   const toastContainer = document.getElementById("toastContainer") || document.createElement("div");
   toastContainer.id = "toastContainer";
   toastContainer.className = "toast-container position-fixed bottom-0 end-0 p-3";
   document.body.appendChild(toastContainer);

   const toastEl = document.createElement("div");
   toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
   toastEl.setAttribute("role", "alert");
   toastEl.setAttribute("aria-live", "assertive");
   toastEl.setAttribute("aria-atomic", "true");

   // Ensure proper text direction for RTL languages
   if (!adminAnalyticsLocale().startsWith("en")) {
     toastEl.setAttribute("dir", "rtl");
   }

   var safeMessage = message ? String(message).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') : '';
   toastEl.innerHTML = `
         <div class="d-flex">
             <div class="toast-body">${safeMessage}</div>
             <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
         </div>
     `;
   toastContainer.appendChild(toastEl);
   const toast = new bootstrap.Toast(toastEl);
   toast.show();
 }

// Auth Helper
// fetchWithAuth is now defined in auth.js

document.addEventListener("DOMContentLoaded", function () {
  const exportForm = document.getElementById("exportForm");
  if (exportForm && !exportForm.dataset.exportHandlerBound) {
    exportForm.addEventListener("submit", handleExport);
    exportForm.dataset.exportHandlerBound = "true";
  }

  // Initialize export dates for either dashboard modal or reports page form.
  const today = new Date();
  const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
  const formatDate = (d) => { const year = d.getFullYear(); const month = String(d.getMonth() + 1).padStart(2, "0"); const day = String(d.getDate()).padStart(2, "0"); return `${year}-${month}-${day}`; };

  const exportStartDate =
    document.getElementById("exportStartDate") || document.getElementById("startDate");
  const exportEndDate =
    document.getElementById("exportEndDate") || document.getElementById("endDate");

  if (exportStartDate && !exportStartDate.value) {
    exportStartDate.value = formatDate(firstDay);
  }
  if (exportEndDate && !exportEndDate.value) {
    exportEndDate.value = formatDate(today);
  }
});

async function handleExport(event) {
  event.preventDefault();

  const reportType =
    document.getElementById("exportReportType")?.value ||
    document.querySelector('input[name="reportType"]:checked')?.value;
  const exportFormat =
    document.getElementById("exportFormat")?.value ||
    document.querySelector('input[name="exportFormat"]:checked')?.value ||
    "CSV";
  const startDate =
    document.getElementById("exportStartDate")?.value ||
    document.getElementById("startDate")?.value;
  const endDate =
    document.getElementById("exportEndDate")?.value || document.getElementById("endDate")?.value;
  const exportBtn =
    event.submitter ||
    document.querySelector('button[type="submit"][form="exportForm"]') ||
    document.querySelector('#exportModal button[type="submit"]');
  const exportSpinner = document.getElementById("exportSpinner");

  if (!reportType) {
    showToast(
      adminAnalyticsText("يرجى اختيار نوع التقرير.", "Please select a report type."),
      "warning"
    );
    return;
  }

  if (!startDate || !endDate) {
    showToast(adminAnalyticsText("يرجى تحديد نطاق تاريخ صالح.", "Please select a valid date range."), "warning");
    return;
  }

  if (exportBtn) exportBtn.disabled = true;
  if (exportSpinner) exportSpinner.classList.remove("d-none");

  const url = "/api/analytics/export/sync";
  try {
    const response = await fetchWithAuth(url, {
      method: "POST",
      body: JSON.stringify({
        report_type: reportType,
        export_format: exportFormat.toUpperCase(),
        filters: {
          period_start: startDate,
          period_end: endDate,
        },
      }),
    });

    if (!response) return; // fetchWithAuth handles 401 redirect

    // Check for job ID if async export
    // For now, assuming direct file download as per current backend /export
    const blob = await response.blob();
    const contentDisposition = response.headers.get("Content-Disposition");
    let filename = `report_${reportType}_${startDate}_${endDate}.csv`;
    if (contentDisposition) {
      const filenameMatch = contentDisposition.match(/filename="(.+)"/);
      if (filenameMatch && filenameMatch[1]) {
        filename = filenameMatch[1];
      }
    }

    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);

    showToast(
      adminAnalyticsText("تم تصدير التقرير بنجاح!", "Report exported successfully!"),
      "success"
    );
    const exportModal = bootstrap.Modal.getInstance(document.getElementById("exportModal"));
    if (exportModal) exportModal.hide();
  } catch (e) {
    console.error("Export failed:", e);
    showToast(
      adminAnalyticsText(
        "فشل تصدير التقرير. يرجى المحاولة مرة أخرى.",
        "Report export failed. Please try again."
      ),
      "error"
    );
  } finally {
    if (exportBtn) exportBtn.disabled = false;
    if (exportSpinner) exportSpinner.classList.add("d-none");
  }
}

async function loadPredictiveInsights(start, end, scopeType, scopeId) {
  try {
    const payload = {
      scope_type: scopeType,
      scope_id: scopeId,
      start_date: start,
      end_date: end,
      horizon_days: getForecastHorizon(),
    };
    const [attendanceRes, incidentsRes, enrollmentRes] = await Promise.all([
      fetchWithAuth(`/api/analytics/predict/attendance`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
      fetchWithAuth(`/api/analytics/predict/incidents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
      fetchWithAuth(`/api/analytics/predict/enrollment`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    ]);

    if (!attendanceRes || !incidentsRes || !enrollmentRes) return;
    const attendanceData = await attendanceRes.json();
    const incidentsData = await incidentsRes.json();
    const enrollmentData = await enrollmentRes.json();

    window.__forecastData = {
      attendance: attendanceData,
      incidents: incidentsData,
      enrollment: enrollmentData,
    };

    updatePredictiveCards(attendanceData, incidentsData, enrollmentData);
    updateModelMeta(attendanceData.model_meta);
    updateTrendCharts(attendanceData.points, incidentsData.points);
  } catch (error) {
    console.error("Predictive insights error", error);
  }
}

function getForecastHorizon() {
  const select = document.getElementById("forecastHorizon");
  const value = select ? parseInt(select.value, 10) : 30;
  return Number.isFinite(value) && value > 0 ? value : 30;
}

async function loadScenarios() {
    const metric = _currentTrendMetric();
    const horizon = getForecastHorizon();
    const periodStart = document.getElementById('periodStart')?.value;
    const periodEnd = document.getElementById('periodEnd')?.value;

    if (!periodStart || !periodEnd) return;

    try {
      const params = new URLSearchParams({
          metric: metric,
          horizon_days: horizon,
          period_start: periodStart,
          period_end: periodEnd
      });

      const response = await fetchWithAuth(`/api/analytics/scenarios?${params}`);
      if (!response.ok) throw new Error('Failed to load scenarios');

      scenarioData = await response.json();

      const legend = document.getElementById('scenarioLegend');
      const stddevEl = document.getElementById('scenarioStddev');
      if (legend && stddevEl && scenarioData.stddev) {
        stddevEl.textContent = adminAnalyticsText(
          `الانحراف المعياري: ${scenarioData.stddev.toFixed(2)}`,
          `Standard deviation: ${scenarioData.stddev.toFixed(2)}`
        );
        legend.classList.remove('d-none');
      }

      renderScenarioOverlay();
    } catch (error) {
      console.error('Error loading scenarios:', error);
    }
}

document.addEventListener('input', function (e) {
  if (e.target && e.target.id === 'whatIfSlider') {
    var v = document.getElementById('whatIfValue');
    if (v) v.textContent = (e.target.value > 0 ? '+' : '') + e.target.value + '%';
  }
});

async function runWhatIf() {
  var slider = document.getElementById('whatIfSlider');
  var resultEl = document.getElementById('whatIfResult');
  if (!slider || !resultEl) return;
  var adjustment = parseFloat(slider.value) || 0;
  var horizon = (typeof getForecastHorizon === 'function') ? getForecastHorizon() : 30;
  var metric = (typeof _currentTrendMetric === 'function') ? _currentTrendMetric() : 'attendance';
  var periodStart = document.getElementById('periodStart') ? document.getElementById('periodStart').value : '';
  var periodEnd = document.getElementById('periodEnd') ? document.getElementById('periodEnd').value : '';
  if (!periodStart || !periodEnd) return;
  resultEl.innerHTML = '<div class="text-muted small">' + adminAnalyticsText('جاري الحساب...', 'Calculating...') + '</div>';
  try {
    var params = new URLSearchParams({ metric: metric, adjustment_percent: adjustment,
      horizon_days: horizon, period_start: periodStart, period_end: periodEnd });
    var res = await fetchWithAuth('/api/analytics/what-if?' + params.toString());
    if (!res.ok) throw new Error('what-if failed');
    var data = await res.json();
    if (!data.summary || data.summary.baseline_end === undefined) {
      resultEl.innerHTML = '<div class="text-muted small">' + adminAnalyticsText('لا توجد بيانات كافية', 'Not enough data') + '</div>';
      return;
    }
    var s = data.summary;
    var favorable = metric === 'incidents' ? (s.delta_absolute < 0) : (s.delta_absolute > 0);
    var arrow = s.delta_absolute > 0 ? 'bi-arrow-up' : (s.delta_absolute < 0 ? 'bi-arrow-down' : 'bi-dash');
    var color = s.delta_absolute === 0 ? 'text-muted' : (favorable ? 'text-success' : 'text-danger');
    resultEl.innerHTML =
      '<div class="d-flex gap-4 flex-wrap">' +
      '<div><div class="text-muted small">' + adminAnalyticsText('الأساسي (النهاية)', 'Baseline (end)') + '</div>' +
      '<div class="fs-5 fw-bold">' + s.baseline_end + '</div></div>' +
      '<div><div class="text-muted small">' + adminAnalyticsText('المعدّل (النهاية)', 'Adjusted (end)') + '</div>' +
      '<div class="fs-5 fw-bold">' + s.adjusted_end + '</div></div>' +
      '<div><div class="text-muted small">' + adminAnalyticsText('الفرق', 'Delta') + '</div>' +
      '<div class="fs-5 fw-bold ' + color + '"><i class="bi ' + arrow + ' me-1"></i>' +
      Math.abs(s.delta_percent).toFixed(1) + '%</div></div></div>';
  } catch (err) {
    resultEl.innerHTML = '<div class="alert alert-warning mb-0">' + adminAnalyticsText('تعذر إجراء التحليل', 'Analysis failed') + '</div>';
  }
}

function renderScenarioOverlay() {
    if (!scenarioData || !trendChartInstance) return;

    const chart = trendChartInstance;
    const scenarios = scenarioData.scenarios;

    chart.data.datasets = chart.data.datasets.filter(ds => !ds._isScenario);

    if (!scenarios || Object.keys(scenarios).length === 0) return;

    const currentType = _currentTrendMetric();
    const forecastPayload = window.__forecastData || {};
    const forecastSeries = forecastPayload[currentType] || {};
    const forecastPoints = forecastSeries.forecast_points || [];

    if (!forecastPoints.length) return;

    const dataSeries = window.__trendData?.[currentType] || [];
    const paddingLength = Math.max(0, dataSeries.length - 1);

    const scenarioConfigs = {
      'scenarioBaseline': { key: 'baseline', label_ar: 'الأساسي', label_en: 'Baseline', color: '#3b82f6', dash: [] },
      'scenarioOptimistic': { key: 'optimistic', label_ar: 'متفائل (+1σ)', label_en: 'Optimistic (+1σ)', color: '#22c55e', dash: [5, 5] },
      'scenarioPessimistic': { key: 'pessimistic', label_ar: 'متشائم (-1σ)', label_en: 'Pessimistic (-1σ)', color: '#ef4444', dash: [5, 5] },
      'scenarioBestCase': { key: 'best_case', label_ar: 'أفضل حالة (+2σ)', label_en: 'Best Case (+2σ)', color: '#16a34a', dash: [10, 5] },
      'scenarioWorstCase': { key: 'worst_case', label_ar: 'أسوأ حالة (-2σ)', label_en: 'Worst Case (-2σ)', color: '#dc2626', dash: [10, 5] }
    };

    const lang = adminAnalyticsText('ar', 'en');

    Object.entries(scenarioConfigs).forEach(([checkboxId, config]) => {
      const checkbox = document.getElementById(checkboxId);
      if (!checkbox || !checkbox.checked) return;

      const scenarioPoints = scenarios[config.key];
      if (!scenarioPoints || scenarioPoints.length === 0) return;

      const historicalNulls = new Array(paddingLength).fill(null);
      const forecastData = scenarioPoints.map(sp => {
        return typeof sp.value === 'number' ? sp.value : parseFloat(sp.value) || 0;
      });
      const data = historicalNulls.concat(forecastData);

      chart.data.datasets.push({
        label: lang === 'en' ? config.label_en : config.label_ar,
        data: data,
        borderColor: config.color,
        backgroundColor: config.color + '20',
        borderWidth: 2,
        borderDash: config.dash,
        pointRadius: 0,
        fill: false,
        tension: 0.3,
        _isScenario: true
      });
    });

    chart.update();
}

document.addEventListener("change", function(e) {
  if (e.target.id && e.target.id.startsWith('scenario')) {
    renderScenarioOverlay();
  }
});

function updateForecastLabels(horizon) {
  const suffix = `(${horizon}d)`;
  document
    .querySelectorAll("[data-forecast-label] .forecast-period-suffix")
    .forEach((el) => {
      el.textContent = suffix;
    });
}

async function updateForecastHorizon() {
  const horizon = getForecastHorizon();
  updateForecastLabels(horizon);

  const start = document.getElementById("periodStart")?.value || "";
  const end = document.getElementById("periodEnd")?.value || "";
  const gov = document.getElementById("governorateFilter")?.value || "";

  if (!start || !end) {
    showToast(
      adminAnalyticsText(
        "يرجى تحديد تاريخ البداية والنهاية أولاً",
        "Please select a start and end date first"
      ),
      "warning"
    );
    return;
  }

  const scopeType = gov ? "GOVERNORATE" : "NETWORK";
  const scopeId = gov || null;

  await loadPredictiveInsights(start, end, scopeType, scopeId);
}

function updatePredictiveCards(attendanceData, incidentsData, enrollmentData) {
  const attendanceForecast = document.getElementById("attendanceForecast");
  const attendanceBand = document.getElementById("attendanceForecastBand");
  const incidentForecast = document.getElementById("incidentForecast");
  const incidentBand = document.getElementById("incidentForecastBand");
  const enrollmentForecast = document.getElementById("enrollmentForecast");
  const enrollmentBand = document.getElementById("enrollmentForecastBand");

  // Validate and format attendance forecast (percentage)
  const attValidation = window.KpiValidation?.validateForecastMetric
    ? window.KpiValidation.validateForecastMetric(attendanceData, "attendance")
    : { valid: true };
  const lastAttendance = attendanceData.forecast_points?.slice(-1)[0];
  if (attendanceForecast && lastAttendance) {
    if (attValidation.valid) {
      const numericValue = Number(lastAttendance.value);
      const value = Number.isFinite(numericValue) ? numericValue.toFixed(1) : "--";
      attendanceForecast.textContent = `${value}%`;
      const lower = attendanceData.confidence?.lower?.slice(-1)[0]?.value ?? 0;
      const upper = attendanceData.confidence?.upper?.slice(-1)[0]?.value ?? 0;
      if (attendanceBand) {
        attendanceBand.textContent = adminAnalyticsText(
          `نطاق الثقة: ${lower.toFixed(1)}% - ${upper.toFixed(1)}%`,
          `Confidence range: ${lower.toFixed(1)}% - ${upper.toFixed(1)}%`
        );
      }
    } else {
      attendanceForecast.innerHTML = `<span class="text-danger-emphasis">${attValidation.message || "غير متاح"}</span>`;
      if (attendanceBand) {
        attendanceBand.textContent = "--";
      }
    }
  }

  // Validate and format incident forecast (count - must be non-negative)
  const incValidation = window.KpiValidation?.validateForecastMetric
    ? window.KpiValidation.validateForecastMetric(incidentsData, "incidents")
    : { valid: true };
  const lastIncident = incidentsData.forecast_points?.slice(-1)[0];
  if (incidentForecast && lastIncident) {
    if (incValidation.valid) {
      const lower = incidentsData.confidence?.lower?.slice(-1)[0]?.value ?? 0;
      const upper = incidentsData.confidence?.upper?.slice(-1)[0]?.value ?? 0;
      incidentForecast.textContent = `${lastIncident.value.toFixed(2)}`;
      if (incidentBand) {
        incidentBand.textContent = adminAnalyticsText(
          `نطاق الثقة: ${lower.toFixed(2)} - ${upper.toFixed(2)}`,
          `Confidence range: ${lower.toFixed(2)} - ${upper.toFixed(2)}`
        );
      }
    } else {
      incidentForecast.innerHTML = `<span class="text-danger-emphasis">${incValidation.message || "غير متاح"}</span>`;
      if (incidentBand) {
        incidentBand.textContent = "--";
      }
    }
  }

  // Validate and format enrollment forecast (count - must be non-negative)
  const enrValidation = window.KpiValidation?.validateForecastMetric
    ? window.KpiValidation.validateForecastMetric(enrollmentData, "enrollment")
    : { valid: true };
  const lastEnrollment = enrollmentData.forecast_points?.slice(-1)[0];
  if (enrollmentForecast && lastEnrollment) {
    if (enrValidation.valid) {
      const lower = enrollmentData.confidence?.lower?.slice(-1)[0]?.value ?? 0;
      const upper = enrollmentData.confidence?.upper?.slice(-1)[0]?.value ?? 0;
      enrollmentForecast.textContent = `${lastEnrollment.value.toFixed(0)}`;
      if (enrollmentBand) {
        enrollmentBand.textContent = adminAnalyticsText(
          `نطاق الثقة: ${lower.toFixed(0)} - ${upper.toFixed(0)}`,
          `Confidence range: ${lower.toFixed(0)} - ${upper.toFixed(0)}`
        );
      }
    } else {
      enrollmentForecast.innerHTML = `<span class="text-danger-emphasis">${enrValidation.message || "غير متاح"}</span>`;
      if (enrollmentBand) {
        enrollmentBand.textContent = "--";
      }
    }
  }
}

function updateModelMeta(meta) {
  const container = document.getElementById("modelMeta");
  if (!container || !meta) return;
  const trainedAt = meta.last_trained || meta.trained_at || "--";
  const version = meta.model_version || "v1";
  const confidence = meta.confidence ? `${(meta.confidence * 100).toFixed(0)}%` : "--";
  const safeTrainedAt = escapeHtml(trainedAt);
  const safeVersion = escapeHtml(version);
  container.innerHTML = `<div class="small text-muted">${adminAnalyticsText(`آخر تدريب: ${safeTrainedAt} | الإصدار: ${safeVersion} | الثقة: ${confidence}`, `Last training: ${safeTrainedAt} | Version: ${safeVersion} | Confidence: ${confidence}`)}</div>`;
}

async function loadModelPerformance() {
  const metrics = ["attendance", "incidents", "enrollment"];
  const results = {};

  for (const metric of metrics) {
    try {
      const response = await fetchWithAuth(`/api/analytics/model-performance?metric=${metric}&days_back=30`);
      if (response && response.ok) {
        results[metric] = await response.json();
      }
    } catch (error) {
      console.error(`Error loading ${metric} performance:`, error);
    }
  }

  renderModelPerformance(results);
}

function renderModelPerformance(results) {
  const container = document.getElementById("modelPerformanceContent");
  if (!container) return;

  const metrics = Object.entries(results);
  if (metrics.length === 0) {
    container.innerHTML = `
      <div class="text-center text-muted py-3">
        <i class="bi bi-info-circle me-2"></i>
        ${adminAnalyticsText("لا توجد بيانات أداء متاحة", "No performance data available")}
      </div>
    `;
    return;
  }

  const lang = adminAnalyticsText("ar", "en");

  container.innerHTML = `
    <div class="row g-3">
      ${metrics
        .map(([metric, data]) => {
          const metricLabel = {
            attendance: lang === "en" ? "Attendance" : "الحضور",
            incidents: lang === "en" ? "Incidents" : "الحوادث",
            enrollment: lang === "en" ? "Enrollment" : "التسجيل",
          }[metric];

          const trendIcon = {
            improving: "bi-arrow-up-circle-fill text-success",
            declining: "bi-arrow-down-circle-fill text-danger",
            stable: "bi-dash-circle-fill text-muted",
            insufficient_data: "bi-question-circle-fill text-warning",
          }[data.trend] || "bi-question-circle-fill text-muted";

          const trendLabel = {
            improving: lang === "en" ? "Improving" : "يتحسن",
            declining: lang === "en" ? "Declining" : "يتراجع",
            stable: lang === "en" ? "Stable" : "مستقر",
            insufficient_data: lang === "en" ? "Insufficient data" : "بيانات غير كافية",
          }[data.trend];

          return `
            <div class="col-md-4">
              <div class="model-perf-metric">
                <div class="d-flex align-items-center justify-content-between mb-2">
                  <span class="fw-bold">${metricLabel}</span>
                  <i class="bi ${trendIcon}" title="${trendLabel}"></i>
                </div>
                ${
                  data.accuracy !== null
                    ? `
                  <div class="d-flex align-items-baseline gap-2">
                    <span class="fs-3 fw-bold text-primary">${data.accuracy.toFixed(1)}%</span>
                    <small class="text-muted">${adminAnalyticsText("دقة", "accuracy")}</small>
                  </div>
                  <div class="text-muted small mt-1">
                    MAPE: ${data.mape.toFixed(2)}% · ${data.evaluations} ${adminAnalyticsText("تقييمات", "evaluations")}
                  </div>
                `
                    : `
                  <div class="text-muted small">
                    <i class="bi ${trendIcon} me-1"></i>
                    ${lang === "en" ? data.message_en : data.message_ar}
                  </div>
                `
                }
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

async function loadAnomalies(start, end, scopeType, scopeId) {
  try {
    const res = await fetchWithAuth(
      `/api/analytics/anomalies?scope_type=${scopeType}&scope_id=${scopeId || ""}&metric_type=attendance&from=${start}&to=${end}`
    );
    if (!res) return;
    const data = await res.json();
    const list = document.getElementById("anomalyList");
    const countBadge = document.getElementById("anomalyCount");
    if (!list) return;
    list.innerHTML = "";
    const items = data.anomalies || [];
    if (countBadge) countBadge.textContent = items.length;
    if (!items.length) {
      list.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا توجد شذوذات خلال الفترة المحددة.", "No anomalies detected for the selected period.")}</div>`;
      return;
    }
    items.slice(0, 5).forEach((item) => {
      const row = document.createElement("div");
      row.className = "list-group-item border-0";
      const severityClass = item.severity === "CRITICAL" ? "bg-danger" :
                          item.severity === "HIGH" ? "bg-warning text-dark" :
                          item.severity === "MEDIUM" ? "bg-warning" : "bg-info text-dark";
      row.innerHTML = `<div class="d-flex justify-content-between">
        <div>
          <div class="fw-semibold">${escapeHtml(item.message)}</div>
          <small class="text-muted">${formatDateForDisplay(item.detected_at)}</small>
        </div>
        <span class="badge ${severityClass}">${formatAnomalySeverity(item.severity)}</span>
      </div>`;
      list.appendChild(row);
    });
  } catch (error) {
    console.error("Anomaly load error", error);
  }
}

async function loadAlerts() {
  const alertList = document.getElementById("alertList");
  const banner = document.getElementById("alertBanner");
  if (!alertList) return;
  alertList.innerHTML = "";

  const combinedAlerts = [];

  // Pull from legacy analytics alerts
  try {
    const res = await fetchWithAuth(`/api/analytics/alerts`);
    if (res) {
      const data = await res.json();
      (data.alerts || []).forEach((a) => combinedAlerts.push({
        message: a.message,
        subtitle: formatMetricType(a.metric_type),
        priority: (a.severity || "MEDIUM").toLowerCase(),
      }));
    }
  } catch (_) {
    // analytics/alerts unavailable — continue with KPI alerts only
  }

  // Pull from KPI-based alerts (new)
  try {
    const res2 = await fetchWithAuth(`/api/kpi/alerts`);
    if (res2) {
      const data2 = await res2.json();
      (data2.alerts || []).forEach((a) => combinedAlerts.push({
        message: a.message_ar || a.message_en || "",
        subtitle: a.type || "",
        priority: a.priority || "medium",
      }));
    }
  } catch (_) {
    // kpi/alerts unavailable — show whatever analytics alerts were collected
  }

  // Sort: critical → high → medium → low
  const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
  combinedAlerts.sort((a, b) => (priorityOrder[a.priority] ?? 3) - (priorityOrder[b.priority] ?? 3));

  // Keep the alert section container visible in both states: when there are
  // alerts the list renders the rows below, and when there are none the list
  // renders its empty-state. (Previously the whole section was hidden with
  // d-none when empty, so the alert list vanished entirely instead of showing
  // "no active alerts".)
  if (banner) {
    banner.classList.remove("d-none");
  }

  if (combinedAlerts.length === 0) {
    window.AdminComponents.renderAsyncState(alertList, "empty", {
      emptyText: adminAnalyticsText("لا توجد تنبيهات نشطة حالياً.", "No active alerts at this time."),
      icon: "bi-bell-slash",
    });
    return;
  }

  combinedAlerts.slice(0, 8).forEach((alert) => {
    const row = document.createElement("div");
    row.className = "list-group-item border-0 py-2";
    const badgeClass = alert.priority === "critical" ? "bg-danger"
      : alert.priority === "high" ? "bg-warning text-dark"
      : alert.priority === "medium" ? "bg-secondary"
      : "bg-info text-dark";
    const badgeLabel = alert.priority === "critical"
      ? adminAnalyticsText("حرج", "Critical")
      : alert.priority === "high"
      ? adminAnalyticsText("عالي", "High")
      : alert.priority === "medium"
      ? adminAnalyticsText("متوسط", "Medium")
      : adminAnalyticsText("منخفض", "Low");
    row.innerHTML = `<div class="d-flex justify-content-between align-items-start gap-2">
      <div class="flex-grow-1">
        <div class="fw-semibold small">${escapeHtml(alert.message)}</div>
        ${alert.subtitle ? `<small class="text-muted">${escapeHtml(alert.subtitle)}</small>` : ""}
      </div>
      <span class="badge ${badgeClass} flex-shrink-0">${badgeLabel}</span>
    </div>`;
    alertList.appendChild(row);
  });
}

async function loadDataQuality() {
  try {
    const res = await fetchWithAuth(`/api/analytics/data-quality`);
    if (!res) return;
    const data = await res.json();
    const scoreEl = document.getElementById("dataQualityScore");
    const statusEl = document.getElementById("dataQualityStatus");
    const pct = (data.completeness_percent ?? 0);
    if (scoreEl) scoreEl.textContent = `${pct.toFixed(1)}%`;

    // The three health bars were previously never updated by this function —
    // they stayed at whatever static value the template happened to render.
    const setBar = (barId, valId, value) => {
      const bar = document.getElementById(barId);
      const val = document.getElementById(valId);
      const v = Number.isFinite(value) ? Math.max(0, Math.min(100, value)) : 0;
      if (bar) bar.style.width = `${v}%`;
      if (val) val.textContent = `${v.toFixed(0)}%`;
    };
    setBar("dqCompBar", "dqCompVal", data.completeness_percent);
    setBar("dqAccBar", "dqAccVal", data.accuracy_score);
    setBar("dqFreshBar", "dqFreshVal", data.timeliness_score);
    const dqCls = pct >= 85 ? "az-badge--green" : pct >= 60 ? "az-badge--amber" : "az-badge--red";
    if (statusEl) {
      statusEl.textContent = pct >= 85
        ? adminAnalyticsText("ممتاز", "Excellent")
        : pct >= 60
          ? adminAnalyticsText("جيد", "Good")
          : adminAnalyticsText("بحاجة تحسين", "Needs improvement");
      statusEl.className = "az-badge " + dqCls;
    }
    // Update the progress ring
    if (typeof window._updateDQRing === 'function') window._updateDQRing(pct);
  } catch (error) {
    console.error("Data quality error", error);
  }
}

async function loadTargets() {
  try {
    const res = await fetchWithAuth(`/api/analytics/targets`);
    if (!res) return;
    const data = await res.json();
    const targetList = document.getElementById("targetList");
    if (!targetList) return;
    targetList.innerHTML = "";
    (data.targets || []).slice(0, 5).forEach((t) => {
      const row = document.createElement("div");
      row.className = "list-group-item border-0";
      row.innerHTML = `<div class="d-flex justify-content-between">
        <span>${escapeHtml(t.metric_type)}</span>
        <span class="fw-semibold">${escapeHtml(t.target_value)}</span>
      </div>`;
      targetList.appendChild(row);
    });
    if (!(data.targets || []).length) {
      targetList.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا توجد أهداف محددة.", "No targets defined.")}</div>`;
    }
  } catch (error) {
    console.error("Targets load error", error);
  }
}

async function loadBenchmarks() {
  try {
    const optionsRes = await fetchWithAuth(`/api/admin/options/kindergartens`);
    if (!optionsRes) return;
    const optionsData = await optionsRes.json();
    const firstKg = (optionsData.kindergartens || optionsData || [])[0];
    const kgId = firstKg?.id || firstKg?.value || null;
    const benchmarkList = document.getElementById("benchmarkList");
    if (!benchmarkList) return;
    if (!kgId) {
      benchmarkList.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا تتوفر بيانات المقارنة.", "Benchmark data is not available.")}</div>`;
      return;
    }
    const res = await fetchWithAuth(`/api/analytics/benchmarks/${kgId}`);
    if (!res) return;
    const data = await res.json();
    benchmarkList.innerHTML = "";
    (data.benchmarks || []).slice(0, 5).forEach((b) => {
      const row = document.createElement("div");
      row.className = "list-group-item border-0";
      row.innerHTML = `<div class="d-flex justify-content-between">
        <span>${escapeHtml(b.metric_type)} (${escapeHtml(b.comparison_group)})</span>
        <span class="fw-semibold">${escapeHtml(b.value)}</span>
      </div>`;
      benchmarkList.appendChild(row);
    });
    if (!(data.benchmarks || []).length) {
      benchmarkList.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا توجد بيانات مقارنة.", "No benchmark data available.")}</div>`;
    }
  } catch (error) {
    console.error("Benchmarks load error", error);
  }
}

async function loadTargetProgress() {
  const metrics = ["attendance_rate", "incident_rate", "governance_score"];
  const governorate = document.getElementById("governorateFilter")?.value;
  const results = {};

  for (const metric of metrics) {
    try {
      const params = new URLSearchParams({ metric });
      if (governorate) params.append("governorate", governorate);

      const response = await fetchWithAuth(`/api/analytics/target-progress?${params}`);
      if (response && response.ok) {
        results[metric] = await response.json();
      }
    } catch (error) {
      console.error(`Error loading ${metric} progress:`, error);
    }
  }

  renderTargetProgress(results);
}

function renderTargetProgress(results) {
  const container = document.getElementById("targetProgressContent");
  if (!container) return;

  const metrics = Object.entries(results);
  if (metrics.length === 0) {
    container.innerHTML = `<div class="text-center text-muted py-3">${adminAnalyticsText("لا توجد بيانات تقدم متاحة", "No progress data available")}</div>`;
    return;
  }

  const lang = adminAnalyticsText("ar", "en");

  container.innerHTML = `<div class="row g-3">${metrics.map(([metric, data]) => {
    const metricLabel = {
      attendance_rate: lang === "en" ? "Attendance Rate" : "معدل الحضور",
      incident_rate: lang === "en" ? "Incident Rate" : "معدل الحوادث",
      governance_score: lang === "en" ? "Governance Score" : "درجة الحوكمة",
    }[metric];

    const statusClass = {
      achieved: "success",
      on_track: "primary",
      at_risk: "warning",
      off_track: "danger",
    }[data.status] || "secondary";

    const statusLabel = {
      achieved: lang === "en" ? "Achieved" : "محقق",
      on_track: lang === "en" ? "On Track" : "على المسار",
      at_risk: lang === "en" ? "At Risk" : "معرض للخطر",
      off_track: lang === "en" ? "Off Track" : "خارج المسار",
    }[data.status];

    const daysText = data.days_to_target === 0
      ? (lang === "en" ? "Target achieved!" : "تم تحقيق الهدف!")
      : data.days_to_target > 0
        ? (lang === "en" ? `${data.days_to_target} days to target` : `${data.days_to_target} يوم للوصول للهدف`)
        : (lang === "en" ? "Moving away from target" : "يبتعد عن الهدف");

    return `<div class="col-md-4">
      <div class="target-progress-item">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <span class="fw-bold">${metricLabel}</span>
          <span class="badge bg-${statusClass}">${statusLabel}</span>
        </div>
        <div class="target-progress-bar mb-2">
          <div class="target-progress-fill bg-${statusClass}" style="width: ${Math.min(100, data.progress_percent)}%"></div>
        </div>
        <div class="d-flex justify-content-between small">
          <span class="text-muted">
            ${data.current_value}${metric === "incident_rate" ? "/100" : "%"}
            <i class="bi bi-arrow-right mx-1"></i>
            ${data.target_value}${metric === "incident_rate" ? "/100" : "%"}
          </span>
          <span class="text-${statusClass}">${daysText}</span>
        </div>
        ${data.percentile !== null ? `<div class="mt-1 small text-muted"><i class="bi bi-trophy me-1"></i>${adminAnalyticsText(`المئوية ${data.percentile}`, `${data.percentile}th percentile`)}</div>` : ""}
        <div class="mt-1 small text-muted">
          <i class="bi bi-speedometer2 me-1"></i>
          ${adminAnalyticsText(`السرعة: ${data.velocity_per_day > 0 ? "+" : ""}${data.velocity_per_day.toFixed(3)}/يوم`, `Velocity: ${data.velocity_per_day > 0 ? "+" : ""}${data.velocity_per_day.toFixed(3)}/day`)}
        </div>
      </div>
    </div>`;
  }).join("")}</div>`;
}

async function loadRecommendations() {
  try {
    const optionsRes = await fetchWithAuth(`/api/admin/options/kindergartens`);
    if (!optionsRes) return;
    const optionsData = await optionsRes.json();
    const firstKg = (optionsData.kindergartens || optionsData || [])[0];
    const kgId = firstKg?.id || firstKg?.value || null;
    const list = document.getElementById("recommendationList");
    if (!list) return;
    if (!kgId) {
      list.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا توجد توصيات متاحة.", "No recommendations available.")}</div>`;
      return;
    }
    const res = await fetchWithAuth(`/api/analytics/recommendations/${kgId}`);
    if (!res) return;
    const data = await res.json();
    list.innerHTML = "";
    (data.recommendations || []).slice(0, 5).forEach((rec) => {
      const row = document.createElement("div");
      row.className = "list-group-item border-0";
      row.innerHTML = `<div class="fw-semibold">${escapeHtml(rec.title)}</div>
        <div class="small text-muted">${escapeHtml(rec.description)}</div>`;
      list.appendChild(row);
    });
    if (!(data.recommendations || []).length) {
      list.innerHTML = `<div class="text-muted small">${adminAnalyticsText("لا توجد توصيات متاحة.", "No recommendations available.")}</div>`;
    }
  } catch (error) {
    console.error("Recommendations load error", error);
  }
}

function getScoreColor(score) {
  if (score >= 80) return "bg-success";
  else if (score >= 60) return "bg-warning";
  return "bg-danger";
}

function renderSparklines(dashboardData) {
  var containers = document.querySelectorAll('.kpi-sparkline');
  if (!containers || containers.length === 0) return;

  containers.forEach(function (el) {
    var metric = el.getAttribute('data-metric');
    var data = getSparklineData(dashboardData, metric);
    if (!data || data.length < 2) {
      el.innerHTML = '';
      return;
    }
    renderMiniSparkline(el, data);
  });
}

function getSparklineData(data, metric) {
  if (!data) return null;

  function validNums(arr) {
    var filtered = (arr || []).filter(function (v) { return v != null && isFinite(v); });
    return filtered.length >= 2 ? filtered : null;
  }

  switch (metric) {
    case 'total_kg':
      return validNums(data.total_kindergartens_trend) || validNums([data.previous_period?.total_kindergartens, data.network_summary?.total_kindergartens]);
    case 'total_children':
      return validNums(data.total_children_trend) || validNums([data.previous_period?.total_children, data.network_summary?.total_children]);
    case 'attendance_rate':
      return validNums(data.attendance_rate_trend) || validNums([data.previous_period?.attendance_rate, data.network_summary?.attendance_rate]);
    case 'incident_rate':
      return validNums(data.incident_rate_trend) || validNums([data.previous_period?.incident_rate, data.network_summary?.incident_rate]);
    default:
      return null;
  }
}

function renderMiniSparkline(container, data) {
  var w = container.offsetWidth || 120;
  var h = 32;
  var padding = 2;
  var min = Math.min.apply(null, data);
  var max = Math.max.apply(null, data);
  var range = max - min || 1;

  var points = data.map(function (v, i) {
    var x = padding + (i / (data.length - 1)) * (w - 2 * padding);
    var y = h - padding - ((v - min) / range) * (h - 2 * padding);
    return x + ',' + y;
  }).join(' ');

  var isUp = data[data.length - 1] >= data[0];
  var color = isUp ? '#22C55E' : '#EF4444';
  var metric = container.getAttribute('data-metric');
  if (metric === 'incident_rate') {
    color = isUp ? '#EF4444' : '#22C55E';
  }

  var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
    '<polyline points="' + points + '" fill="none" stroke="' + color + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>' +
    '</svg>';
  container.innerHTML = svg;
}

// =============================================================================
// Registration Analytics
// =============================================================================

let funnelChartInstance = null;
let sourceChartInstance = null;
let regTablePage = 1;
let regTableTotalPages = 1;

function getRegistrationFilters() {
  return {
    status: document.getElementById("regStatusFilter")?.value || "",
    source: document.getElementById("regSourceFilter")?.value || "",
    reviewer_id: document.getElementById("regReviewerFilter")?.value || "",
  };
}

async function loadRegistrationAnalytics() {
  const start = document.getElementById("periodStart")?.value || "";
  const end = document.getElementById("periodEnd")?.value || "";
  const gov = document.getElementById("governorateFilter")?.value || "";
  const filters = getRegistrationFilters();

  if (!start || !end) return;

  const params = new URLSearchParams({ start_date: start, end_date: end });
  if (gov) params.set("governorate", gov);
  if (filters.status) params.set("status", filters.status);
  if (filters.source) params.set("source", filters.source);
  if (filters.reviewer_id) params.set("reviewer_id", filters.reviewer_id);

  try {
    const res = await fetchWithAuth(`/api/analytics/registration/analytics?${params.toString()}`);
    if (!res) return;
    const data = await res.json();
    updateRegistrationKPIs(data);
    renderFunnelChart(data.funnel || {});
    renderRejectionReasons(data.rejection_reasons || {});
    renderSourceChart(data.source_breakdown || {});
    regTablePage = 1;
    await loadRegistrationTable();
  } catch (error) {
    console.error("Registration analytics load error:", error);
  }

  // Load entity-level summary (users / KGs / children / quality) and quality breakdown in parallel
  await Promise.all([
    loadRegistrationEntitySummary(),
    loadRegistrationQualityBreakdown(),
  ]);
}

// =============================================================================
// Registration Entity Summary — users, KGs, children, quality, action queue
// =============================================================================

async function loadRegistrationEntitySummary() {
  const start = document.getElementById("periodStart")?.value || "";
  const end   = document.getElementById("periodEnd")?.value   || "";
  const gov   = document.getElementById("governorateFilter")?.value || "";

  if (!start || !end) return;

  const params = new URLSearchParams({ start_date: start, end_date: end });
  if (gov) params.set("governorate", gov);

  try {
    const res = await fetchWithAuth(`/api/analytics/registration/entity-summary?${params}`);
    if (!res) return;
    const data = await res.json();

    _renderEntitySummaryCards(data);
    _renderStatusMatrix(data.enrollments || {});
    _renderActionQueue(data.actions_required || []);
    _renderRoleBreakdown(data.users?.by_role || {});

    const freshEl = document.getElementById("regStatusFreshness");
    if (freshEl) {
      const ts = new Date().toLocaleTimeString(adminAnalyticsLocale());
      freshEl.textContent = adminAnalyticsText(
        `آخر تحديث: ${ts}`,
        `Last updated: ${ts}`
      );
    }
  } catch (err) {
    console.error("Entity summary load error:", err);
  }
}

function _setBarWidth(id, pct) {
  const el = document.getElementById(id);
  if (el) el.style.width = `${Math.min(100, Math.max(0, pct || 0)).toFixed(1)}%`;
}

function _renderEntitySummaryCards(data) {
  const u      = data.users          || {};
  const k      = data.kindergartens  || {};
  const c      = data.children       || {};
  const locale = adminAnalyticsLocale();

  // Users
  safeSetText("regUsersTotal",     (u.total     || 0).toLocaleString(locale));
  safeSetText("regUsersNew",       `+${(u.new_this_period || 0).toLocaleString(locale)}`);
  safeSetText("regUsersActive",    (u.active    || 0).toLocaleString(locale));
  safeSetText("regUsersSuspended", (u.suspended || 0).toLocaleString(locale));
  safeSetText("regUsersInactive",  (u.inactive  || 0).toLocaleString(locale));
  const uT = u.total || 1;
  _setBarWidth("regUsersActiveBar",    (u.active    || 0) / uT * 100);
  _setBarWidth("regUsersSuspendedBar", (u.suspended || 0) / uT * 100);
  _setBarWidth("regUsersInactiveBar",  (u.inactive  || 0) / uT * 100);

  // Kindergartens
  safeSetText("regKgTotal",    (k.total    || 0).toLocaleString(locale));
  safeSetText("regKgNew",      `+${(k.new_this_period || 0).toLocaleString(locale)}`);
  safeSetText("regKgActive",   (k.active   || 0).toLocaleString(locale));
  safeSetText("regKgInactive", (k.inactive || 0).toLocaleString(locale));
  safeSetText("regKgDraft",    (k.draft    || 0).toLocaleString(locale));
  const kT = k.total || 1;
  _setBarWidth("regKgActiveBar",   (k.active   || 0) / kT * 100);
  _setBarWidth("regKgInactiveBar", (k.inactive || 0) / kT * 100);
  _setBarWidth("regKgDraftBar",    (k.draft    || 0) / kT * 100);

  // Children
  safeSetText("regChildrenTotal",         (c.total              || 0).toLocaleString(locale));
  safeSetText("regChildrenEnrolled",      (c.enrolled           || 0).toLocaleString(locale));
  safeSetText("regChildrenEnrolledCount", (c.enrolled           || 0).toLocaleString(locale));
  safeSetText("regChildrenPending",       (c.pending            || 0).toLocaleString(locale));
  safeSetText("regChildrenNone",          (c.without_enrollment || 0).toLocaleString(locale));
  const cT = c.total || 1;
  _setBarWidth("regChildrenEnrolledBar", (c.enrolled           || 0) / cT * 100);
  _setBarWidth("regChildrenPendingBar",  (c.pending            || 0) / cT * 100);
  _setBarWidth("regChildrenNoEnrollBar", (c.without_enrollment || 0) / cT * 100);
}

function _renderStatusMatrix(enrollments) {
  const container = document.getElementById("regStatusMatrix");
  if (!container) return;

  const byStatus = enrollments.by_status || {};
  const total    = enrollments.total     || 1;
  const locale   = adminAnalyticsLocale();

  const STATUSES = [
    { key: "DRAFT",          ar: "مسودة",            en: "Draft",          color: "#94A3B8", icon: "bi-file-earmark" },
    { key: "SUBMITTED",      ar: "مقدّم",            en: "Submitted",      color: "#3B82F6", icon: "bi-send" },
    { key: "PENDING_REVIEW", ar: "قيد المراجعة",     en: "Pending Review", color: "#F59E0B", icon: "bi-hourglass-split" },
    { key: "ACCEPTED",       ar: "مقبول",            en: "Accepted",       color: "#10B981", icon: "bi-check-circle" },
    { key: "ACTIVE",         ar: "نشط",              en: "Active",         color: "#059669", icon: "bi-circle-fill" },
    { key: "REJECTED",       ar: "مرفوض",            en: "Rejected",       color: "#EF4444", icon: "bi-x-circle" },
    { key: "WAITLISTED",     ar: "قائمة الانتظار",   en: "Waitlisted",     color: "#6366F1", icon: "bi-clock-history" },
    { key: "WITHDRAWN",      ar: "منسحب",            en: "Withdrawn",      color: "#64748B", icon: "bi-dash-circle" },
  ];

  container.innerHTML = STATUSES.map(s => {
    const count = byStatus[s.key] || 0;
    const pct   = ((count / total) * 100).toFixed(1);
    const label = adminAnalyticsText(s.ar, s.en);
    return `
      <div class="mb-2">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <small class="d-flex align-items-center gap-1 fw-medium" style="font-size:.72rem;">
            <i class="bi ${s.icon}" style="color:${s.color};font-size:.6rem;" aria-hidden="true"></i>
            ${label}
          </small>
          <small style="color:${s.color};font-weight:600;font-size:.72rem;">
            ${count.toLocaleString(locale)}
            <span class="text-muted fw-normal">(${pct}%)</span>
          </small>
        </div>
        <div class="progress" style="height:4px;"
             role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"
             aria-label="${label}: ${pct}%">
          <div class="progress-bar" style="width:${pct}%;background:${s.color};transition:width .4s ease;"></div>
        </div>
      </div>`;
  }).join("");
}

function _renderActionQueue(actions) {
  const container = document.getElementById("regActionQueue");
  const badge     = document.getElementById("regActionsBadge");
  if (!container) return;

  if (badge) {
    badge.textContent = actions.length;
    badge.className   = `badge ms-auto ${actions.length > 0 ? "bg-warning text-dark" : "bg-secondary"}`;
  }

  if (!actions.length) {
    container.innerHTML = `
      <div class="text-center py-3">
        <i class="bi bi-check-circle-fill text-success" style="font-size:2rem;" aria-hidden="true"></i>
        <div class="small text-muted mt-2">
          ${adminAnalyticsText("لا توجد إجراءات مطلوبة حالياً", "No actions required")}
        </div>
      </div>`;
    return;
  }

  const priorityBadge = { high: "danger", medium: "warning text-dark", low: "info text-dark" };
  const locale = adminAnalyticsLocale();

  container.innerHTML = actions.map(a => `
    <div class="d-flex align-items-start gap-2 mb-2 p-2 rounded"
         style="background:rgba(0,0,0,.04);">
      <span class="badge bg-${priorityBadge[a.priority] || "secondary"} flex-shrink-0 mt-1">
        ${(a.count || 0).toLocaleString(locale)}
      </span>
      <div class="flex-grow-1 min-w-0">
        <div class="small fw-medium lh-sm" style="font-size:.75rem;">
          ${escapeHtml(a.label_ar || "")}
        </div>
        ${a.url ? `
          <a href="${escapeHtml(a.url)}"
             class="small text-primary text-decoration-none d-inline-flex align-items-center gap-1 mt-1"
             style="font-size:.68rem;">
            ${escapeHtml(a.action_ar || adminAnalyticsText("عرض", "View"))}
            <i class="bi bi-arrow-left-short" aria-hidden="true"></i>
          </a>` : ""}
      </div>
    </div>`).join("");
}

function _renderRoleBreakdown(byRole) {
  const container = document.getElementById("regRoleBreakdown");
  if (!container) return;

  const ROLES = [
    { key: "ADMIN",      ar: "مدير النظام",    en: "Admin",      color: "#4F46E5", icon: "bi-shield-lock" },
    { key: "MANAGER",    ar: "مدير حضانة",      en: "Manager",    color: "#2563EB", icon: "bi-person-workspace" },
    { key: "SUPERVISOR", ar: "مشرف تربوي",     en: "Supervisor", color: "#7C3AED", icon: "bi-binoculars" },
    { key: "PARENT",     ar: "ولي أمر",        en: "Parent",     color: "#0891B2", icon: "bi-people" },
  ];

  const total  = Object.values(byRole).reduce((a, b) => a + b, 0) || 1;
  const locale = adminAnalyticsLocale();

  container.innerHTML = ROLES.map(r => {
    const count = byRole[r.key] || 0;
    const pct   = ((count / total) * 100).toFixed(1);
    const label = adminAnalyticsText(r.ar, r.en);
    return `
      <div class="d-flex align-items-center gap-2 mb-3">
        <div class="rounded-circle d-flex align-items-center justify-content-center flex-shrink-0"
             style="width:30px;height:30px;background:${r.color}1a;" aria-hidden="true">
          <i class="bi ${r.icon}" style="color:${r.color};font-size:.75rem;"></i>
        </div>
        <div class="flex-grow-1 min-w-0">
          <div class="d-flex justify-content-between align-items-center mb-1">
            <small class="fw-medium" style="font-size:.75rem;">${label}</small>
            <small class="fw-bold" style="color:${r.color};font-size:.75rem;">${count.toLocaleString(locale)}</small>
          </div>
          <div class="progress" style="height:4px;"
               role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"
               aria-label="${label}: ${pct}%">
            <div class="progress-bar" style="width:${pct}%;background:${r.color};transition:width .4s ease;"></div>
          </div>
        </div>
      </div>`;
  }).join("");
}

function updateRegistrationKPIs(data) {
  safeSetText("regTotalApplications", (data.total_applications || 0).toLocaleString(adminAnalyticsLocale()));
  safeSetText("regNewApplications", (data.new_applications || 0).toLocaleString(adminAnalyticsLocale()));
  safeSetText("regApproved", (data.status_breakdown?.ACCEPTED || 0).toLocaleString(adminAnalyticsLocale()));
  safeSetText("regPending", (data.status_breakdown?.PENDING_REVIEW || 0).toLocaleString(adminAnalyticsLocale()));
  safeSetText("regRejected", (data.status_breakdown?.REJECTED || 0).toLocaleString(adminAnalyticsLocale()));
  safeSetText("regConversionValue", `${data.conversion_rate ?? 0}%`);
  safeSetText("regRejectionValue", `${data.approval_workflow?.rejection_rate ?? 0}%`);
  safeSetText("regApprovalTimeValue", `${data.approval_workflow?.avg_approval_hours ?? 0}h`);
  const ohFunnel = document.getElementById("ohFunnelRate");
  if (ohFunnel) {
    const rate = Number(data.conversion_rate ?? 0);
    ohFunnel.textContent = rate.toFixed(1) + "%";
    ohFunnel.className = `fw-bold fs-5 ${rate >= 70 ? "text-success" : rate >= 40 ? "text-warning" : "text-danger"}`;
  }
}

function renderFunnelChart(funnel) {
  const canvas = document.getElementById("funnelChart");
  const empty = document.getElementById("funnelEmpty");
  if (!canvas) return;

  const stages = [
    { label: adminAnalyticsText("مسودة", "Draft"), value: funnel.draft || 0, color: "#94A3B8" },
    { label: adminAnalyticsText("مقدّم", "Submitted"), value: funnel.submitted || 0, color: "#3B82F6" },
    { label: adminAnalyticsText("قيد المراجعة", "Pending Review"), value: funnel.pending_review || 0, color: "#F59E0B" },
    { label: adminAnalyticsText("مقبول", "Accepted"), value: funnel.accepted || 0, color: "#10B981" },
    { label: adminAnalyticsText("نشط", "Active"), value: funnel.active || 0, color: "#059669" },
  ];

  const hasData = stages.some(s => s.value > 0);
  if (empty) empty.classList.toggle("d-none", hasData);
  if (!hasData) {
    if (funnelChartInstance) { funnelChartInstance.destroy(); funnelChartInstance = null; }
    return;
  }

  if (!adminAnalyticsHasChart()) return;

  if (funnelChartInstance) funnelChartInstance.destroy();

  funnelChartInstance = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: stages.map(s => s.label),
      datasets: [{
        label: adminAnalyticsText("الطلبات", "Applications"),
        data: stages.map(s => s.value),
        backgroundColor: stages.map(s => s.color),
        borderWidth: 0,
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { stepSize: 1 } },
        y: { grid: { display: false } },
      },
    },
  });
}

function renderRejectionReasons(reasons) {
  const container = document.getElementById("rejectionReasonsList");
  const empty = document.getElementById("rejectionEmpty");
  if (!container) return;

  const entries = Object.entries(reasons).sort((a, b) => b[1] - a[1]).slice(0, 10);
  const hasData = entries.length > 0;
  if (empty) empty.classList.toggle("d-none", hasData);

  if (!hasData) {
    container.innerHTML = "";
    return;
  }

  const maxCount = entries[0][1];
  container.innerHTML = entries.map(([reason, count]) => `
    <div class="list-group-item border-0 px-0">
      <div class="d-flex justify-content-between align-items-center mb-1">
        <small class="fw-medium text-truncate" style="max-width: 70%;" title="${escapeHtml(reason)}">${escapeHtml(reason)}</small>
        <span class="badge bg-danger rounded-pill">${count}</span>
      </div>
      <div class="progress" style="height: 4px;">
        <div class="progress-bar bg-danger" style="width: ${(count / maxCount) * 100}%"></div>
      </div>
    </div>
  `).join("");
}

function renderSourceChart(sources) {
  const canvas = document.getElementById("sourceChart");
  const empty = document.getElementById("sourceEmpty");
  if (!canvas) return;

  const entries = Object.entries(sources);
  const hasData = entries.length > 0;
  if (empty) empty.classList.toggle("d-none", hasData);

  if (!hasData) {
    if (sourceChartInstance) { sourceChartInstance.destroy(); sourceChartInstance = null; }
    return;
  }

  if (!adminAnalyticsHasChart()) return;
  if (sourceChartInstance) sourceChartInstance.destroy();

  const colors = ["#4F46E5", "#0EA5E9", "#10B981", "#F59E0B", "#EF4444", "#6366F1"];
  sourceChartInstance = new window.Chart(canvas, {
    type: "doughnut",
    data: {
      labels: entries.map(e => e[0]),
      datasets: [{
        data: entries.map(e => e[1]),
        backgroundColor: entries.map((_, i) => colors[i % colors.length]),
        borderWidth: 2,
        borderColor: "#fff",
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, padding: 8, font: { size: 11 } } },
      },
    },
  });
}

async function loadRegistrationTable() {
  const tbody = document.getElementById("registrationTableBody");
  const info = document.getElementById("regTableInfo");
  if (!tbody) return;

  const start = document.getElementById("periodStart")?.value || "";
  const end = document.getElementById("periodEnd")?.value || "";
  const gov = document.getElementById("governorateFilter")?.value || "";
  const filters = getRegistrationFilters();
  const search = document.getElementById("regSearchInput")?.value || "";

  const params = new URLSearchParams({
    start_date: start,
    end_date: end,
    page: regTablePage,
    page_size: 10,
  });
  if (gov) params.set("governorate", gov);
  if (filters.status) params.set("status", filters.status);
  if (filters.source) params.set("source", filters.source);
  if (filters.reviewer_id) params.set("reviewer_id", filters.reviewer_id);
  if (search) params.set("search", search);

  try {
    const res = await fetchWithAuth(`/api/analytics/registration/drilldown?${params.toString()}`);
    if (!res) return;
    const data = await res.json();
    regTableTotalPages = data.pagination?.total_pages || 1;

    const statusBadge = (status) => {
      const map = {
        DRAFT: "bg-secondary",
        SUBMITTED: "bg-info",
        PENDING_REVIEW: "bg-warning text-dark",
        ACCEPTED: "bg-success",
        REJECTED: "bg-danger",
        ACTIVE: "bg-primary",
        WAITLISTED: "bg-info",
        WITHDRAWN: "bg-secondary",
      };
      return map[status] || "bg-secondary";
    };

    tbody.innerHTML = (data.data || []).map(item => `
      <tr>
        <td class="fw-medium">${escapeHtml(item.child_name)}</td>
        <td>${escapeHtml(item.parent_name)}</td>
        <td>${escapeHtml(item.kindergarten_name)}</td>
        <td>${escapeHtml(item.kindergarten_city)}</td>
        <td><span class="badge ${statusBadge(item.status)}">${escapeHtml(item.status)}</span></td>
        <td>${escapeHtml(item.source || "-")}</td>
        <td>${item.submitted_at ? new Date(item.submitted_at).toLocaleDateString(adminAnalyticsLocale()) : "-"}</td>
        <td>${escapeHtml(item.reviewer_name || "-")}</td>
        <td class="text-center">
          <a href="/enrollments/${item.id}" class="btn btn-sm btn-outline-primary" title="${adminAnalyticsText('عرض', 'View')}" aria-label="${adminAnalyticsText('عرض طلب', 'View application')}: ${escapeHtml(item.child_name || '')}">
            <i class="bi bi-eye" aria-hidden="true"></i>
          </a>
        </td>
      </tr>
    `).join("") || `<tr><td colspan="9" class="text-center py-4 text-muted">${adminAnalyticsText("لا تتوفر بيانات للفترة أو المعايير المحددة. يرجى تعديل عوامل التصفية أو اختيار نطاق زمني مختلف.", "No data")}</td></tr>`;

    if (info) {
      info.textContent = adminAnalyticsText(
        `الصفحة ${data.pagination?.page || 1} من ${data.pagination?.total_pages || 1}`,
        `Page ${data.pagination?.page || 1} of ${data.pagination?.total_pages || 1}`
      );
    }

    document.getElementById("regPrevPage")?.toggleAttribute("disabled", (data.pagination?.page || 1) <= 1);
    document.getElementById("regNextPage")?.toggleAttribute("disabled", (data.pagination?.page || 1) >= regTableTotalPages);
  } catch (error) {
    console.error("Registration table load error:", error);
    tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-danger">${adminAnalyticsText("تعذر تحميل البيانات. (الرجاء إعادة المحاولة)", "Failed to load data. (Please retry)")}</td></tr>`;
  }
}

async function loadReviewerOptions() {
  const select = document.getElementById("regReviewerFilter");
  if (!select) return;
  try {
    const res = await fetchWithAuth(`/api/admin/users?role=MANAGER&limit=100`);
    if (!res) return;
    const data = await res.json();
    const users = data.data || [];
    const current = select.value;
    // Keep the first option
    select.innerHTML = `<option value="">${adminAnalyticsText("كل المُراجعين", "All Reviewers")}</option>`;
    users.forEach(u => {
      const opt = document.createElement("option");
      opt.value = u.id;
      opt.textContent = u.full_name || u.username;
      select.appendChild(opt);
    });
    if (current) select.value = current;
  } catch (error) {
    console.error("Reviewer options load error:", error);
  }
}

// Wire up registration filters
document.addEventListener("DOMContentLoaded", function () {
  const regStatus = document.getElementById("regStatusFilter");
  const regSource = document.getElementById("regSourceFilter");
  const regReviewer = document.getElementById("regReviewerFilter");
  const regSearch = document.getElementById("regSearchInput");
  const regRefresh = document.getElementById("regRefreshTable");
  const regPrev = document.getElementById("regPrevPage");
  const regNext = document.getElementById("regNextPage");

  [regStatus, regSource, regReviewer].forEach(el => {
    el?.addEventListener("change", () => {
      regTablePage = 1;
      loadRegistrationAnalytics();
    });
  });

  regSearch?.addEventListener("input", () => {
    regTablePage = 1;
    loadRegistrationTable();
  });

  regRefresh?.addEventListener("click", () => loadRegistrationAnalytics());
  regPrev?.addEventListener("click", () => {
    if (regTablePage > 1) { regTablePage--; loadRegistrationTable(); }
  });
  regNext?.addEventListener("click", () => {
    if (regTablePage < regTableTotalPages) { regTablePage++; loadRegistrationTable(); }
  });

  loadReviewerOptions();

  document.getElementById("regEntityRefreshBtn")?.addEventListener("click", () => {
    loadRegistrationEntitySummary();
    loadRegistrationQualityBreakdown();
  });
});

// =============================================================================
// Registration Quality Breakdown — governorate table, completeness, monthly trend
// =============================================================================

let _regMonthlyChart = null;

async function loadRegistrationQualityBreakdown() {
  const start = document.getElementById("periodStart")?.value || "";
  const end   = document.getElementById("periodEnd")?.value   || "";
  const gov   = document.getElementById("governorateFilter")?.value || "";

  if (!start || !end) return;

  const params = new URLSearchParams({ start_date: start, end_date: end });
  if (gov) params.set("governorate", gov);

  try {
    const res = await fetchWithAuth(`/api/analytics/registration/quality-breakdown?${params}`);
    if (!res) return;
    const data = await res.json();
    _renderGovernorateBreakdown(data.governorate_breakdown || []);
    _renderCompletenessPanel(data.completeness || {});
    _renderMonthlyTrendChart(data.monthly_trends || {});
  } catch (err) {
    console.error("Quality breakdown load error:", err);
    const tbody = document.getElementById("regGovTableBody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-center py-3 text-danger small">
      ${adminAnalyticsText("تأخرت البيانات", "Data delayed")}
    </td></tr>`;
  }
}

function _renderGovernorateBreakdown(rows) {
  const tbody   = document.getElementById("regGovTableBody");
  const counter = document.getElementById("regGovCount");
  const sub     = document.getElementById("regGovSubtitle");
  if (!tbody) return;

  if (counter) counter.textContent = `${rows.length}`;
  if (sub) {
    const hasDraft = rows.some(r => r.kg_draft > 0);
    const hasPend  = rows.some(r => r.enrollments_pending > 0);
    sub.textContent = hasDraft || hasPend
      ? adminAnalyticsText("توجد محافظات تحتاج اهتماماً", "Some governorates need attention")
      : adminAnalyticsText("جميع المحافظات في وضع جيد", "All governorates in good standing");
    sub.style.color = (hasDraft || hasPend) ? "#D97706" : "#10B981";
  }

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">
      ${adminAnalyticsText("لا توجد بيانات محافظات", "No governorate data")}
    </td></tr>`;
    return;
  }

  const locale = adminAnalyticsLocale();
  tbody.innerHTML = rows.map(r => {
    const pct   = r.completion_rate || 0;
    const color = pct >= 75 ? "#10B981" : pct >= 50 ? "#F59E0B" : "#EF4444";
    const draftBadge = r.kg_draft > 0
      ? `<span class="badge" style="background:#FEF9C3;color:#92400E;font-size:.65rem;">${r.kg_draft}</span>`
      : `<span class="text-muted" style="font-size:.8rem;">—</span>`;
    const pendBadge = r.enrollments_pending > 0
      ? `<span class="badge" style="background:#FEE2E2;color:#991B1B;font-size:.65rem;">${r.enrollments_pending.toLocaleString(locale)}</span>`
      : `<span class="text-muted" style="font-size:.8rem;">—</span>`;
    return `
      <tr>
        <td class="fw-medium" style="font-size:.8rem;">${escapeHtml(r.governorate)}</td>
        <td class="text-center" style="font-size:.8rem;">${r.kg_total.toLocaleString(locale)}</td>
        <td class="text-center">
          <span class="badge" style="background:#D1FAE5;color:#065F46;font-size:.65rem;">${r.kg_active}</span>
        </td>
        <td class="text-center">${draftBadge}</td>
        <td class="text-center" style="font-size:.8rem;">${r.enrollments_total.toLocaleString(locale)}</td>
        <td class="text-center">${pendBadge}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <div class="progress flex-grow-1" style="height:5px;"
                 role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
              <div class="progress-bar" style="width:${pct}%;background:${color};"></div>
            </div>
            <small style="color:${color};font-weight:600;font-size:.72rem;min-width:32px;">${pct}%</small>
          </div>
        </td>
      </tr>`;
  }).join("");
}

function _renderCompletenessPanel(comp) {
  const container = document.getElementById("regCompletenessPanel");
  const badge     = document.getElementById("avgCompletenessBadge");
  if (!container) return;

  const ITEMS = [
    { key: "parent_profiles",   ar: "ملفات أولياء الأمور",      en: "Parent Profiles",   color: "#2563EB", icon: "bi-person-vcard" },
    { key: "children_profiles", ar: "ملفات الأطفال",            en: "Children Profiles", color: "#0891B2", icon: "bi-emoji-smile" },
    { key: "kg_licensed",       ar: "الحضانات المرخصة",          en: "Licensed KGs",      color: "#4F46E5", icon: "bi-patch-check" },
    { key: "kg_geolocated",     ar: "الحضانات محددة جغرافياً",   en: "Geolocated KGs",   color: "#7C3AED", icon: "bi-geo-alt" },
    { key: "staff_profiles",    ar: "ملفات الموظفين والمشرفين", en: "Staff Profiles",    color: "#D97706", icon: "bi-person-workspace" },
  ];

  const pcts = ITEMS.map(i => comp[i.key]?.pct || 0);
  const avg  = pcts.length ? Math.round(pcts.reduce((a, b) => a + b, 0) / pcts.length) : 0;
  if (badge) {
    badge.textContent = `${avg}%`;
    badge.className = `badge border fw-semibold ${
      avg >= 80 ? "bg-success-subtle text-success border-success-subtle"
      : avg >= 60 ? "bg-warning-subtle text-warning border-warning-subtle"
      : "bg-danger-subtle text-danger border-danger-subtle"}`;
  }

  const locale = adminAnalyticsLocale();
  container.innerHTML = ITEMS.map(item => {
    const d     = comp[item.key] || { total: 0, complete: 0, pct: 0 };
    const pct   = d.pct || 0;
    const color = pct >= 80 ? "#10B981" : pct >= 60 ? "#F59E0B" : "#EF4444";
    const label = adminAnalyticsText(item.ar, item.en);
    return `
      <div class="mb-3">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <div class="d-flex align-items-center gap-1">
            <i class="bi ${item.icon}" style="color:${item.color};font-size:.65rem;" aria-hidden="true"></i>
            <small class="fw-medium" style="font-size:.75rem;">${label}</small>
          </div>
          <div class="d-flex align-items-center gap-1">
            <small style="color:${color};font-weight:700;font-size:.72rem;">${pct.toFixed(1)}%</small>
            <small class="text-muted" style="font-size:.66rem;">(${d.complete}/${d.total})</small>
          </div>
        </div>
        <div class="progress" style="height:5px;"
             role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"
             aria-label="${label}: ${pct.toFixed(1)}%">
          <div class="progress-bar" style="width:${pct}%;background:${color};transition:width .5s ease;"></div>
        </div>
      </div>`;
  }).join("");
}

function _renderMonthlyTrendChart(trends) {
  const canvas = document.getElementById("regMonthlyTrendChart");
  const empty  = document.getElementById("regTrendEmpty");
  if (!canvas) return;

  const labels = trends.labels || [];
  const hasData = labels.length > 0 && (
    (trends.users        || []).some(v => v > 0) ||
    (trends.enrollments  || []).some(v => v > 0) ||
    (trends.kindergartens || []).some(v => v > 0)
  );

  if (empty) empty.classList.toggle("d-none", hasData);

  if (!hasData) {
    if (_regMonthlyChart) { _regMonthlyChart.destroy(); _regMonthlyChart = null; }
    return;
  }

  if (!adminAnalyticsHasChart()) return;
  if (_regMonthlyChart) _regMonthlyChart.destroy();

  const locale = adminAnalyticsLocale();
  const displayLabels = labels.map(l => {
    const [yr, mo] = l.split("-");
    return new Date(parseInt(yr, 10), parseInt(mo, 10) - 1, 1)
      .toLocaleDateString(locale, { month: "short", year: "2-digit" });
  });

  _regMonthlyChart = new window.Chart(canvas, {
    type: "line",
    data: {
      labels: displayLabels,
      datasets: [
        {
          label: adminAnalyticsText("مستخدمون جدد", "New Users"),
          data: trends.users || [],
          borderColor: "#2563EB",
          backgroundColor: "rgba(37,99,235,.07)",
          tension: 0.35,
          fill: true,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
        },
        {
          label: adminAnalyticsText("طلبات تسجيل", "Enrollments"),
          data: trends.enrollments || [],
          borderColor: "#0891B2",
          backgroundColor: "rgba(8,145,178,.06)",
          tension: 0.35,
          fill: true,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 2,
        },
        {
          label: adminAnalyticsText("حضانات جديدة", "New KGs"),
          data: trends.kindergartens || [],
          borderColor: "#4F46E5",
          backgroundColor: "transparent",
          tension: 0.35,
          fill: false,
          pointRadius: 3,
          pointHoverRadius: 5,
          borderWidth: 1.5,
          borderDash: [5, 4],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          rtl: document.documentElement.dir === "rtl",
          callbacks: {
            title: ctx => ctx[0]?.label || "",
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          title: { display: true, text: adminAnalyticsText("التاريخ", "Date"), color: "#6c757d" },
          ticks: { font: { size: 10 }, maxRotation: 0 },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: adminAnalyticsText("القيمة (العدد أو النسبة %)", "Value (Count or %)"), color: "#6c757d" },
          ticks: { font: { size: 10 }, stepSize: 1 },
          grid: { color: "rgba(0,0,0,.04)" },
        },
      },
    },
  });
}

window.addEventListener("languageChanged", () => {
  if (document.getElementById("periodStart") && document.getElementById("periodEnd")) {
    loadAdminAnalytics();
  }
});

function exportTableToCSV(tableId, filename) {
  const table = document.getElementById(tableId);
  if (!table) return;
  let csv = [];
  for (let i = 0; i < table.rows.length; i++) {
    let row = [], cols = table.rows[i].querySelectorAll("td, th");
    for (let j = 0; j < cols.length; j++) {
      let data = cols[j].innerText.replace(/(\r\n|\n|\r)/gm, "").replace(/,/g, "");
      row.push('"' + data + '"');
    }
    csv.push(row.join(","));
  }
  let csvFile = new Blob([csv.join("\n")], {type: "text/csv;charset=utf-8;"});
  let downloadLink = document.createElement("a");
  downloadLink.download = filename;
  downloadLink.href = window.URL.createObjectURL(csvFile);
  downloadLink.style.display = "none";
  document.body.appendChild(downloadLink);
  downloadLink.click();
  document.body.removeChild(downloadLink);
}

async function loadActionQueue() {
    const periodStart = document.getElementById('periodStart')?.value;
    const periodEnd = document.getElementById('periodEnd')?.value;
    const governorate = document.getElementById('governorateFilter')?.value;

    if (!periodStart || !periodEnd) return;

    try {
        const params = new URLSearchParams({
            period_start: periodStart,
            period_end: periodEnd
        });
        if (governorate) params.append('governorate', governorate);

        const response = await fetchWithAuth(`/api/analytics/action-queue?${params}`);
        if (!response.ok) throw new Error('Failed to load action queue');

        const data = await response.json();
        renderActionQueue(data.actions || []);
    } catch (error) {
        console.error('Error loading action queue:', error);
        document.getElementById('actionQueueList').innerHTML = `
            <div class="alert alert-warning mb-0">
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${adminAnalyticsText('تعذر تحميل قائمة الإجراءات', 'Unable to load action queue')}
            </div>
        `;
    }
}

function renderActionQueue(actions) {
    const container = document.getElementById('actionQueueList');
    const countBadge = document.getElementById('actionCount');

    if (!actions || actions.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-check-circle-fill fs-1 text-success mb-2"></i>
                <p class="mb-0">${adminAnalyticsText('لا توجد إجراءات مطلوبة', 'No actions required')}</p>
            </div>
        `;
        countBadge.textContent = '0';
        return;
    }

    countBadge.textContent = actions.length;

    const lang = adminAnalyticsText('ar', 'en');

    container.innerHTML = actions.map(action => {
        const priorityClass = {
            'HIGH': 'danger',
            'MEDIUM': 'warning',
            'LOW': 'info'
        }[action.priority] || 'secondary';

        const title = adminAnalyticsEscape(lang === 'en' ? action.title_en : action.title_ar);
        const description = adminAnalyticsEscape(lang === 'en' ? action.description_en : action.description_ar);
        const deadline = new Date(action.deadline).toLocaleDateString(lang === 'en' ? 'en-US' : 'ar-JO');
        const link = adminAnalyticsEscape(adminAnalyticsInternalLink(action.link));
        const icon = adminAnalyticsIcon(action.icon);

        return `
            <div class="action-item action-item--${priorityClass.toLowerCase()} mb-3">
                <div class="d-flex align-items-start gap-3">
                    <div class="action-icon">
                        <i class="bi ${icon} text-${priorityClass} fs-4"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex align-items-center gap-2 mb-2">
                            <span class="badge bg-${priorityClass}">${adminAnalyticsEscape(formatAnomalySeverity(action.priority))}</span>
                            <small class="text-muted">
                                <i class="bi bi-calendar-event me-1"></i>
                                ${adminAnalyticsText('الموعد النهائي:', 'Deadline:')} ${deadline}
                            </small>
                            ${action.affected_count > 0 ? `
                                <small class="text-muted ms-2">
                                    <i class="bi bi-building me-1"></i>
                                    ${action.affected_count} ${adminAnalyticsText('كيان', 'entities')}
                                </small>
                            ` : ''}
                        </div>
                        <p class="mb-1 fw-bold">${title}</p>
                        <p class="mb-2 text-muted small">${description}</p>
                        <div class="d-flex gap-2">
                            <a href="${link}" class="btn btn-sm btn-outline-${priorityClass}">
                                <i class="bi bi-eye me-1"></i>
                                ${adminAnalyticsText('عرض', 'View')}
                            </a>
                            <button class="btn btn-sm btn-${priorityClass}" onclick="createActionPlan()">
                                <i class="bi bi-plus-circle me-1"></i>
                                ${adminAnalyticsText('إنشاء خطة عمل', 'Create Action Plan')}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function createActionPlan() {
    window.location.href = '/admin/governance/reminders';
}

async function loadInsights() {
    const periodStart = document.getElementById('periodStart')?.value;
    const periodEnd = document.getElementById('periodEnd')?.value;
    const governorate = document.getElementById('governorateFilter')?.value;

    if (!periodStart || !periodEnd) return;

    try {
        const params = new URLSearchParams({
            period_start: periodStart,
            period_end: periodEnd
        });
        if (governorate) params.append('governorate', governorate);

        const response = await fetchWithAuth(`/api/analytics/insights?${params}`);
        if (!response.ok) throw new Error('Failed to load insights');

        const data = await response.json();
        renderInsights(data.insights || []);
    } catch (error) {
        console.error('Error loading insights:', error);
        document.getElementById('insightsList').innerHTML = `
            <div class="alert alert-warning mb-0">
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${adminAnalyticsText('تعذر تحميل الرؤى', 'Unable to load insights')}
            </div>
        `;
    }
}

function renderInsights(insights) {
    const container = document.getElementById('insightsList');
    const countBadge = document.getElementById('insightsCount');

    if (!insights || insights.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-check-circle-fill fs-1 text-success mb-2"></i>
                <p class="mb-0">${adminAnalyticsText('لا توجد مشكلات تتطلب الانتباه', 'No issues requiring attention')}</p>
            </div>
        `;
        countBadge.textContent = '0';
        return;
    }

    countBadge.textContent = insights.length;

    const lang = adminAnalyticsText('ar', 'en');

    container.innerHTML = insights.map(insight => {
        const severityClass = {
            'HIGH': 'danger',
            'MEDIUM': 'warning',
            'LOW': 'info'
        }[insight.severity] || 'secondary';

        const message = adminAnalyticsEscape(lang === 'en' ? insight.message_en : insight.message_ar);
        const action = adminAnalyticsEscape(lang === 'en' ? insight.action_en : insight.action_ar);
        const link = adminAnalyticsEscape(adminAnalyticsInternalLink(insight.link));
        const icon = adminAnalyticsIcon(insight.icon);
        const typeArg = encodeURIComponent(String(insight.type || ''));

        return `
            <div class="insight-card insight-card--${severityClass.toLowerCase()} mb-3">
                <div class="d-flex align-items-start gap-3">
                    <div class="insight-icon">
                        <i class="bi ${icon} text-${severityClass} fs-4"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex align-items-center gap-2 mb-2">
                            <span class="badge bg-${severityClass}">${adminAnalyticsEscape(formatAnomalySeverity(insight.severity))}</span>
                            ${insight.affected_count > 0 ? `
                                <small class="text-muted">
                                    <i class="bi bi-building me-1"></i>
                                    ${insight.affected_count} ${adminAnalyticsText('كيان متأثر', 'affected entities')}
                                </small>
                            ` : ''}
                        </div>
                        <p class="mb-2 fw-bold">${message}</p>
                        <p class="mb-2 text-muted small">${action}</p>
                        <div class="d-flex gap-2">
                            <a href="${link}" class="btn btn-sm btn-outline-${severityClass}">
                                <i class="bi bi-arrow-right me-1"></i>
                                ${adminAnalyticsText('عرض التفاصيل', 'View Details')}
                            </a>
                            <button class="btn btn-sm btn-outline-secondary" onclick="analyzeRootCause(decodeURIComponent('${typeArg}'))">
                                <i class="bi bi-search me-1"></i>
                                ${adminAnalyticsText('تحليل السبب', 'Analyze Root Cause')}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function loadPredictiveAlerts() {
    const container = document.getElementById('predictiveAlertsList');
    if (!container) return;
    const governorate = document.getElementById('governorateFilter')?.value;
    try {
        const params = new URLSearchParams({ horizon_days: '14', lookback_days: '60' });
        if (governorate) params.set('governorate', governorate);
        const response = await fetchWithAuth(`/api/analytics/predictive-alerts?${params}`);
        if (!response.ok) throw new Error('Failed to load predictive alerts');
        const data = await response.json();
        renderPredictiveAlerts(data.alerts || []);
    } catch (error) {
        console.error('Error loading predictive alerts:', error);
        container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsText('تعذر تحميل التنبيهات التنبؤية', 'Unable to load predictive alerts')}</div>`;
    }
}

function renderPredictiveAlerts(alerts) {
    const container = document.getElementById('predictiveAlertsList');
    const countBadge = document.getElementById('predictiveAlertsCount');
    if (!container) return;
    const lang = adminAnalyticsText('ar', 'en');

    if (!alerts || alerts.length === 0) {
        if (countBadge) countBadge.classList.add('d-none');
        container.innerHTML = `<div class="analytics-empty-state">
            <i class="bi bi-check-circle-fill text-success me-2"></i>
            ${adminAnalyticsText('لا توجد مؤشرات مهددة بتجاوز أهدافها', 'No metrics are projected to breach their targets')}
        </div>`;
        return;
    }

    if (countBadge) { countBadge.textContent = alerts.length; countBadge.classList.remove('d-none'); }
    container.innerHTML = alerts.map(a => {
        const sev = { HIGH: 'danger', MEDIUM: 'warning', LOW: 'info' }[a.severity] || 'secondary';
        const message = lang === 'en' ? a.message_en : a.message_ar;
        const conf = (a.confidence !== null && a.confidence !== undefined)
            ? `${Math.round(a.confidence * 100)}%` : '—';
        return `
            <div class="insight-card insight-card--${sev} mb-3">
                <div class="d-flex align-items-start gap-3">
                    <div class="insight-icon"><i class="bi ${a.icon} text-${sev} fs-4"></i></div>
                    <div class="flex-grow-1 min-w-0">
                        <div class="d-flex align-items-center gap-2 mb-2 flex-wrap">
                            <span class="badge bg-${sev}">${escapeHtml(formatAnomalySeverity(a.severity))}</span>
                            <small class="text-muted"><i class="bi bi-calendar-event me-1"></i>${adminAnalyticsText('خلال', 'in')} ${a.days_until_breach} ${adminAnalyticsText('يوم', 'days')}</small>
                            <small class="text-muted ms-2"><i class="bi bi-bullseye me-1"></i>${adminAnalyticsText('الثقة', 'confidence')}: ${conf}</small>
                        </div>
                        <p class="mb-0 fw-bold">${escapeHtml(message)}</p>
                    </div>
                </div>
            </div>`;
    }).join('');
}

async function loadNarrativeSummary() {
    const container = document.getElementById('narrativeList');
    if (!container) return;
    const periodStart = document.getElementById('periodStart')?.value;
    const periodEnd = document.getElementById('periodEnd')?.value;
    const governorate = document.getElementById('governorateFilter')?.value;
    if (!periodStart || !periodEnd) return;
    try {
        const params = new URLSearchParams({ period_start: periodStart, period_end: periodEnd });
        if (governorate) params.set('governorate', governorate);
        const response = await fetchWithAuth(`/api/analytics/narrative-summary?${params}`);
        if (!response.ok) throw new Error('Failed to load narrative');
        const data = await response.json();
        renderNarrativeSummary(data.sentences || []);
    } catch (error) {
        console.error('Error loading narrative summary:', error);
        container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsText('تعذر تحميل الملخص السردي', 'Unable to load the narrative summary')}</div>`;
    }
}

function renderNarrativeSummary(sentences) {
    const container = document.getElementById('narrativeList');
    if (!container) return;
    const lang = adminAnalyticsText('ar', 'en');
    if (!sentences.length) {
        container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsText('لا يوجد ملخص متاح', 'No summary available')}</div>`;
        return;
    }
    const toneColor = { positive: 'success', warning: 'warning', negative: 'danger', neutral: 'secondary' };
    container.innerHTML = sentences.map(s => {
        const text = lang === 'en' ? s.en : s.ar;
        return `<div class="narrative-line narrative-line--${s.tone}">
            <i class="bi ${s.icon} text-${toneColor[s.tone] || 'secondary'}"></i>
            <span>${escapeHtml(text)}</span>
        </div>`;
    }).join('');
}

async function loadDataLineage() {
    const container = document.getElementById('dataLineageList');
    if (!container) return;
    try {
        const response = await fetchWithAuth('/api/analytics/data-lineage');
        if (!response.ok) throw new Error('Failed to load data lineage');
        const data = await response.json();
        renderDataLineage(data.sources || []);
    } catch (error) {
        console.error('Error loading data lineage:', error);
        container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsText('تعذر تحميل مصادر البيانات', 'Unable to load data sources')}</div>`;
    }
}

function renderDataLineage(sources) {
    const container = document.getElementById('dataLineageList');
    if (!container) return;
    const lang = adminAnalyticsText('ar', 'en');
    if (!sources.length) {
        container.innerHTML = `<div class="analytics-empty-state">${adminAnalyticsText('لا توجد مصادر', 'No sources')}</div>`;
        return;
    }
    const statusLabel = {
        fresh: adminAnalyticsText('حديث', 'Fresh'),
        recent: adminAnalyticsText('حديث نسبيًا', 'Recent'),
        stale: adminAnalyticsText('قديم', 'Stale'),
        empty: adminAnalyticsText('فارغ', 'Empty'),
        unknown: adminAnalyticsText('غير معروف', 'Unknown'),
    };
    const statusIcon = { fresh: 'bi-check-circle-fill', recent: 'bi-clock-fill', stale: 'bi-exclamation-triangle-fill', empty: 'bi-slash-circle', unknown: 'bi-question-circle' };
    container.innerHTML = sources.map(s => {
        const name = lang === 'en' ? s.name_en : s.name_ar;
        const updated = s.last_updated
            ? `${adminAnalyticsText('آخر تحديث', 'Updated')}: ${new Date(s.last_updated).toLocaleDateString(adminAnalyticsLocale())}${s.freshness_days != null ? ` (${adminAnalyticsText(`منذ ${s.freshness_days} يوم`, `${s.freshness_days}d ago`)})` : ''}`
            : adminAnalyticsText('لا توجد سجلات', 'No records');
        return `<div class="lineage-source">
            <div class="d-flex justify-content-between align-items-start mb-1 gap-2">
                <span class="fw-bold">${escapeHtml(name)}</span>
                <span class="lineage-status lineage-status--${s.status}"><i class="bi ${statusIcon[s.status] || 'bi-question-circle'}"></i>${escapeHtml(statusLabel[s.status] || s.status)}</span>
            </div>
            <div class="lineage-source__count">${Number(s.record_count).toLocaleString(adminAnalyticsLocale())}</div>
            <div class="small text-muted"><code>${escapeHtml(s.table)}</code></div>
            <div class="small text-muted mt-1">${escapeHtml(updated)}</div>
        </div>`;
    }).join('');
}

function insightTypeToMetric(insightType) {
    if (insightType.includes('ATTENDANCE')) return 'attendance_rate';
    if (insightType.includes('INCIDENT')) return 'incident_rate';
    if (insightType.includes('GOVERNANCE')) return 'governance_score';
    return null;
}

async function analyzeRootCause(insightType) {
    const metric = insightTypeToMetric(insightType);
    if (!metric) return;

    const periodStart = document.getElementById('periodStart')?.value;
    const periodEnd = document.getElementById('periodEnd')?.value;
    const governorate = document.getElementById('governorateFilter')?.value;

    if (!periodStart || !periodEnd) return;

    const modalHtml = `
        <div class="modal fade" id="rootCauseModal" tabindex="-1">
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">
                            <i class="bi bi-search me-2"></i>
                            ${adminAnalyticsText('تحليل الأسباب الجذرية', 'Root Cause Analysis')}
                        </h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                    </div>
                    <div class="modal-body" id="rootCauseContent">
                        <div class="text-center py-4">
                            <div class="spinner-border text-primary" role="status"></div>
                            <p class="mt-2 text-muted">${adminAnalyticsText('جاري التحليل...', 'Analyzing...')}</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const existingModal = document.getElementById('rootCauseModal');
    if (existingModal) existingModal.remove();

    document.body.insertAdjacentHTML('beforeend', modalHtml);
    const modal = new bootstrap.Modal(document.getElementById('rootCauseModal'));
    modal.show();

    try {
        const params = new URLSearchParams({
            metric: metric,
            period_start: periodStart,
            period_end: periodEnd
        });
        if (governorate) params.append('governorate', governorate);

        const response = await fetchWithAuth(`/api/analytics/root-cause?${params}`);
        if (!response.ok) throw new Error('Root cause analysis failed');

        const data = await response.json();
        renderRootCauseAnalysis(data);
    } catch (error) {
        console.error('Root cause error:', error);
        document.getElementById('rootCauseContent').innerHTML = `
            <div class="alert alert-danger">
                <i class="bi bi-exclamation-triangle me-2"></i>
                ${adminAnalyticsText('تعذر إجراء التحليل', 'Analysis failed')}
            </div>
        `;
    }
}

function renderRootCauseAnalysis(data) {
    const container = document.getElementById('rootCauseContent');
    const lang = adminAnalyticsText('ar', 'en');

    if (!data.factors || data.factors.length === 0) {
        container.innerHTML = `
            <div class="text-center text-muted py-4">
                <i class="bi bi-check-circle-fill fs-1 text-success mb-2"></i>
                <p>${adminAnalyticsText('لم يتم العثور على أسباب جذرية واضحة', 'No significant root causes identified')}</p>
            </div>
        `;
        return;
    }

    const maxImpact = Math.max(...data.factors.map(f => f.impact_score));

    let html = `
        <div class="mb-4">
            <h6 class="text-muted mb-3">
                <i class="bi bi-bar-chart-fill me-1"></i>
                ${adminAnalyticsText('العوامل المساهمة', 'Contributing Factors')}
            </h6>
            <div class="root-cause-factors">
    `;

    data.factors.forEach((factor, idx) => {
        const factorName = lang === 'en' ? factor.factor_en : factor.factor_ar;
        const detail = lang === 'en' ? factor.detail_en : factor.detail_ar;
        const severityClass = {
            'HIGH': 'danger',
            'MEDIUM': 'warning',
            'LOW': 'info'
        }[factor.severity] || 'secondary';

        const barWidth = (factor.impact_score / maxImpact) * 100;

        html += `
            <div class="root-cause-factor mb-3">
                <div class="d-flex align-items-center gap-2 mb-1">
                    <i class="bi ${factor.icon} text-${severityClass}"></i>
                    <span class="fw-bold">${factorName}</span>
                    <span class="badge bg-${severityClass} ms-auto">${factor.severity}</span>
                </div>
                <div class="root-cause-bar mb-1">
                    <div class="root-cause-bar-fill bg-${severityClass}" style="width: ${barWidth}%"></div>
                </div>
                <small class="text-muted">${detail}</small>
            </div>
        `;
    });

    html += `</div></div>`;

    if (data.recommendations && data.recommendations.length > 0) {
        html += `
            <div>
                <h6 class="text-muted mb-3">
                    <i class="bi bi-lightbulb-fill me-1"></i>
                    ${adminAnalyticsText('التوصيات', 'Recommendations')}
                </h6>
                <div class="list-group">
        `;

        data.recommendations.forEach(rec => {
            const recText = lang === 'en' ? rec.recommendation_en : rec.recommendation_ar;
            const priorityClass = {
                'HIGH': 'danger',
                'MEDIUM': 'warning',
                'LOW': 'info'
            }[rec.priority] || 'secondary';

            html += `
                <div class="list-group-item">
                    <div class="d-flex align-items-center gap-2">
                        <span class="badge bg-${priorityClass}">${rec.priority}</span>
                        <span>${recText}</span>
                    </div>
                </div>
            `;
        });

        html += `</div></div>`;
    }

    container.innerHTML = html;
}

// CYBERLUME Export Modal Integration
document.addEventListener('exportData', async function(e) {
    const { format, range } = e.detail;

    // Determine date range based on 'range'
    let startDate = document.getElementById("periodStart")?.value;
    let endDate = document.getElementById("periodEnd")?.value;

    if (range === 'all') {
        // Fallback or explicit 'all time' if backend supports it. For now, we pass empty dates
        // to let backend decide, or set a wide range. We'll set empty strings.
        startDate = "";
        endDate = "";
    }

    // Report type comes from the #exportReportType <select> populated by export_modal(report_types=...)
    const reportType = document.getElementById("exportReportType")?.value || "full_audit";

    showToast(adminAnalyticsText("جاري تحضير الملف...", "Preparing export..."), "info");

    try {
        const response = await fetchWithAuth("/api/analytics/export/sync", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                report_type: reportType,
                export_format: format.toUpperCase(),
                filters: {
                    period_start: startDate,
                    period_end: endDate,
                    range: range
                }
            })
        });

        if (!response) return;

        const blob = await response.blob();
        const contentDisposition = response.headers.get("Content-Disposition");
        let filename = `export_${reportType}_${format}.csv`;
        
        if (contentDisposition) {
            const filenameMatch = contentDisposition.match(/filename="(.+)"/) || contentDisposition.match(/filename=(.+)/);
            if (filenameMatch && filenameMatch[1]) {
                filename = filenameMatch[1].replace(/"/g, '');
            }
        } else if (format.toUpperCase() === "EXCEL") {
            filename = `export_${reportType}.xlsx`;
        }
        
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);

        showToast(adminAnalyticsText("تم التصدير بنجاح", "Exported successfully"), "success");
    } catch (error) {
        console.error("Export failed:", error);
        showToast(adminAnalyticsText("فشل التصدير", "Export failed"), "error");
    }
});

// Persist active tab across page reloads
(function() {
  var saved = sessionStorage.getItem('analyticsActiveTab');
  if (saved) {
    var el = document.querySelector('[data-bs-target="' + saved + '"]');
    if (el) { bootstrap.Tab.getOrCreateInstance(el).show(); }
  }
  document.getElementById('analyticsTabsNav')?.addEventListener('shown.bs.tab', function(e) {
    sessionStorage.setItem('analyticsActiveTab', e.target.getAttribute('data-bs-target'));
  });
})();
