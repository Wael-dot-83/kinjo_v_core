
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

var lastDashboardData = null;
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

    fetchWithAuth("/api/admin/options/governorates")
      .then((res) => {
        if (!res) return;
        return res.json ? res.json() : res;
      })
      .then((data) => {
        if (!data) return;
        const locale = adminAnalyticsLocale();
        (data.governorates || []).forEach((g) => {
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
  const value = option.id ?? option.value ?? option.name ?? option.label ?? "";
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

    // Update all dashboard components
    lastDashboardData = data;
    updateNetworkSummary(data.network_summary);
    updateTrendCharts(data.attendance_trend, data.incident_trend);
    updateGovernorateBreakdown(data.governorate_breakdown);
    updateRiskRadar(data.risk_radar);
    const dist = data.governance_distribution || {};
    updateGovernanceChart(dist.green || 0, dist.amber || 0, dist.red || 0);

    const scopeType = gov ? "GOVERNORATE" : "NETWORK";
    const scopeId = gov || null;

    // These 9 widgets are independent of the primary KPIs above and of each
    // other -- each fetches its own data, owns its own DOM subtree, and
    // already has its own internal try/catch. Awaiting them one at a time
    // meant a single slow call (e.g. the leaderboard scan inside
    // loadComparativeAnalysis) gated every widget queued behind it, even
    // ones that resolve in milliseconds once reached. allSettled (not
    // Promise.all) so one widget's unexpected rejection can't affect the
    // others' already-in-flight requests.
    await Promise.allSettled([
      loadComparativeAnalysis(start, end),
      loadPredictiveInsights(start, end, scopeType, scopeId),
      loadAnomalies(start, end, scopeType, scopeId),
      loadAlerts(),
      loadDataQuality(),
      loadTargets(),
      loadBenchmarks(),
      loadRecommendations(),
      loadRegistrationAnalytics(),
    ]);

    showToast(
      adminAnalyticsText("تم تحديث البيانات بنجاح", "Data refreshed successfully"),
      "success"
    );
    // Update last-updated timestamp
    updateLastUpdatedTimestamp();

    // Fire event for v2 enhancement layer
    document.dispatchEvent(new CustomEvent('analyticsDataLoaded', {
      detail: Object.assign({}, data, {
        __period__: { start: start, end: end }
      })
    }));
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

function updateTrendCharts(attendanceData, incidentData) {
  const ctx = document.getElementById("trendChart");
  if (!ctx) return;

  // Show loading overlay, hide error
  const overlay = document.getElementById("trendChartOverlay");
  const errorDiv = document.getElementById("trendChartError");
  if (overlay) overlay.classList.remove("d-none");
  if (errorDiv) errorDiv.classList.remove("show");

  if (!adminAnalyticsHasChart()) {
    if (overlay) overlay.classList.add("d-none");
    if (errorDiv) {
      errorDiv.classList.add("show");
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
  rows.slice(0, 12).forEach((row) => {
    const score = Number.isFinite(Number(row.governance_score)) ? Number(row.governance_score) : 0;
    const colorClass = score >= 80 ? "bg-success" : score >= 60 ? "bg-warning" : "bg-danger";
    const cell = document.createElement("div");
    cell.className = "col-6 col-md-4";
    cell.innerHTML = `
      <div class="p-2 rounded text-white ${colorClass}" style="cursor:pointer;">
        <div class="small fw-semibold">${adminAnalyticsLiteral(row.governorate)}</div>
        <div class="small">${score.toFixed(1)}%</div>
      </div>
    `;
    cell.addEventListener("click", () => {
      window.location.href = `/admin/analytics/drilldown/GOVERNORATE/${row.governorate}`;
    });
    container.appendChild(cell);
  });
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
      horizon_days: 30,
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

  if (combinedAlerts.length && banner) {
    banner.classList.remove("d-none");
    banner.textContent = adminAnalyticsText(
      `يوجد ${combinedAlerts.length} تنبيه نشط يتطلب المراجعة.`,
      `${combinedAlerts.length} active alert(s) require review.`
    );
  } else if (banner) {
    banner.classList.add("d-none");
  }

  if (combinedAlerts.length === 0) {
    alertList.innerHTML =
      '<div class="az-empty" style="padding:16px 0">' +
      '<i class="bi bi-bell-slash"></i>' +
      '<span class="az-empty__text">' +
      adminAnalyticsText("لا توجد تنبيهات نشطة حالياً.", "No active alerts at this time.") +
      "</span></div>";
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
          <a href="/enrollments/${item.id}" class="btn btn-sm btn-outline-primary" title="{% if ui_lang == 'en' %}View{% else %}عرض{% endif %}">
            <i class="bi bi-eye"></i>
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


// CYBERLUME Export Modal Integration
document.addEventListener('exportData', async function(e) {
    const { format, range } = e.detail;
    
    // Determine date range based on 'range'
    let startDate = document.getElementById("startDate")?.value;
    let endDate = document.getElementById("endDate")?.value;
    
    if (range === 'all') {
        // Fallback or explicit 'all time' if backend supports it. For now, we pass empty dates
        // to let backend decide, or set a wide range. We'll set empty strings.
        startDate = "";
        endDate = "";
    }
    
    // Default report type is overview/full_audit if not specified
    const reportType = document.querySelector('input[name="reportType"]:checked')?.value || "full_audit";
    
    showToast(adminAnalyticsText("جاري تحضير الملف...", "Preparing export..."), "info");
    
    try {
        const response = await fetchWithAuth("/api/analytics/export/sync", {
            method: "POST",
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
