// safeChartData() is provided globally by chart_utils.js (loaded before this script).

var lastDashboardData = null;
var fetchWithAuth = window.fetchWithAuth || async function adminAnalyticsFetchFallback(url, options) {
  const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options || {}));
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

function adminAnalyticsText(arText, enText) {
  const lang =
    window.AdminI18n?.getCurrentLanguage?.().code ||
    localStorage.getItem("admin_language") ||
    localStorage.getItem("kinjo_lang") ||
    document.documentElement.lang ||
    "ar";
  return String(lang).toLowerCase().startsWith("en") ? enText : arText;
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

    // Load comparative analysis
    await loadComparativeAnalysis(start, end);

    const scopeType = gov ? "GOVERNORATE" : "NETWORK";
    const scopeId = gov || null;
    await loadPredictiveInsights(start, end, scopeType, scopeId);
    await loadAnomalies(start, end, scopeType, scopeId);
    await loadAlerts();
    await loadDataQuality();
    await loadTargets();
    await loadBenchmarks();
    await loadRecommendations();

    showToast(
      adminAnalyticsText("تم تحديث البيانات بنجاح", "Data refreshed successfully"),
      "success"
    );
    // Update last-updated timestamp
    updateLastUpdatedTimestamp();
  } catch (error) {
    console.error("Analytics load error:", error);

    // Hide overlay, show error state
    const overlay = document.getElementById("trendChartOverlay");
    const errorDiv = document.getElementById("trendChartError");
    if (overlay) overlay.classList.add("d-none");
    if (errorDiv) errorDiv.classList.add("show");

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
  document.querySelector("#enrollmentRateBar").style.width = "0%";
  document.querySelector("#kpiKgGrowth").innerHTML = '<div class="skeleton-text w-75"></div>';

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
  document.getElementById("topPerformersList").innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;
  document.getElementById("lowPerformersList").innerHTML = `
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
        <div class="list-group-item text-muted text-center py-3 skeleton-row">
            <div class="skeleton-text w-75 mx-auto mb-2"></div>
            <div class="skeleton-text w-50 mx-auto"></div>
        </div>
    `;

  // Clear charts if they exist
  if (trendChartInstance) trendChartInstance.destroy();
  if (governanceChart) governanceChart.destroy();
}

function hideSkeletonLoaders() {
  // KPI cards are updated by updateNetworkSummary which will overwrite skeletons
  // Governorate table is updated by updateGovernorateBreakdown
  // Risk radar is updated by updateRiskRadar
  // Comparative analysis is updated by loadComparativeAnalysis
  // Charts are re-initialized when data loads.
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
  safeSetText("incidentRate", incidentRate.toFixed(2));

  const enrollmentRate = summary.enrollment_rate || 0;
  safeSetText("enrollmentRate", enrollmentRate.toFixed(1) + "%");

  // Update progress bars
  const enrollmentBar = document.getElementById("enrollmentRateBar");
  if (enrollmentBar) {
    enrollmentBar.style.width = Math.min(enrollmentRate, 100) + "%";
    enrollmentBar.className = `progress-bar ${enrollmentRate > 90 ? "bg-success" : enrollmentRate > 70 ? "bg-info" : "bg-warning"}`;
  }

  updateTrendIndicators(summary);
  if (lastDashboardData) {
    lastDashboardData.network_summary = summary;
    renderSparklines(lastDashboardData);
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

  const unavailableText = adminAnalyticsText(
    "غير متوفر للفترة السابقة",
    "No previous-period data"
  );

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
  const className = isNeutral ? "text-muted" : isImprovement ? "text-success" : "text-danger";
  const label = adminAnalyticsText("عن الفترة السابقة", "vs previous period");
  const ariaLabel = isNeutral
    ? adminAnalyticsText("لا تغيير عن الفترة السابقة", "No change vs previous period")
    : isImprovement
      ? adminAnalyticsText(`تحسن بنسبة ${percent}% عن الفترة السابقة`, `Increased by ${percent}% vs previous period`)
      : adminAnalyticsText(`انخفاض بنسبة ${percent}% عن الفترة السابقة`, `Decreased by ${percent}% vs previous period`);

  element.className = className;
  element.setAttribute("aria-label", ariaLabel);
  element.innerHTML = `<i class="bi ${icon} me-1" aria-hidden="true"></i>${isNeutral ? "—" : (delta.delta_percent < 0 ? "-" : "+")}${percent}% ${label}`;
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

  const lineColor = type === "attendance" ? "#198754" : "#fd7e14";
  const lineLabel =
    type === "attendance"
      ? adminAnalyticsText("عدد الحضور", "Attendance count")
      : adminAnalyticsText("عدد الحوادث", "Incident count");

  return {
    data: {
      labels: fullLabels,
      datasets: [
        {
          label: lineLabel,
          data: safeChartData(dataSeries.map((d) => d.value)),
          borderColor: lineColor,
          backgroundColor:
            type === "attendance" ? "rgba(25, 135, 84, 0.1)" : "rgba(253, 126, 20, 0.1)",
          yAxisID: "y",
          fill: true,
          tension: 0.4,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: lineColor,
          pointBorderColor: "#fff",
          pointBorderWidth: 2,
        },
        {
          label: adminAnalyticsText("توقعات", "Forecast"),
          data: new Array(dataSeries.length - 1)
            .fill(null)
            .concat(forecastPoints.map((d) => d.value)),
          borderColor: "#0d6efd",
          borderDash: [6, 4],
          fill: false,
          pointRadius: 2,
        },
        {
          label: adminAnalyticsText("حد أدنى", "Lower bound"),
          data: new Array(dataSeries.length - 1)
            .fill(null)
            .concat((confidence.lower || []).map((d) => d.value)),
          borderColor: "rgba(13,110,253,0.2)",
          backgroundColor: "rgba(13,110,253,0.1)",
          fill: "+1",
          pointRadius: 0,
        },
        {
          label: adminAnalyticsText("حد أعلى", "Upper bound"),
          data: new Array(dataSeries.length - 1)
            .fill(null)
            .concat((confidence.upper || []).map((d) => d.value)),
          borderColor: "rgba(13,110,253,0.2)",
          backgroundColor: "rgba(13,110,253,0.1)",
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
          backgroundColor: "rgba(0,0,0,0.8)",
          titleColor: "#fff",
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

  const validRiskItems = riskData.filter(function (item) {
    if (!item) return false;
    const name = typeof item.name === "string" ? item.name.trim() : "";
    const kindergarten = typeof item.kindergarten === "string" ? item.kindergarten.trim() : "";
    const reason = typeof item.reason === "string" ? item.reason.trim() : "";
    const placeholderValues = new Set([
      "غير محدد",
      "غير متاح",
      "سبب غير محدد",
      "Not specified",
      "Unavailable",
      "Unspecified reason",
    ]);
    const hasValidName = name.length > 0 && !placeholderValues.has(name);
    const hasValidKindergarten = kindergarten.length > 0 && !placeholderValues.has(kindergarten);
    const hasValidScore = Number.isFinite(Number(item.risk_score)) && item.risk_score >= 0 && item.risk_score <= 100;
    const hasValidReason = reason.length > 0 && !placeholderValues.has(reason);
    const noCorruptedText = window.KpiValidation
      ? !window.KpiValidation.containsCorruptedArabic(item.name) &&
        !window.KpiValidation.containsCorruptedArabic(item.kindergarten) &&
        !window.KpiValidation.containsCorruptedArabic(item.reason)
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

  // Sort by risk score descending
  validRiskItems.sort(function (a, b) { return (b.risk_score || 0) - (a.risk_score || 0); });

  validRiskItems.forEach(function (item) {
    const li = document.createElement("li");
    li.className = "list-group-item d-flex justify-content-between align-items-center border-0 py-3";

    const riskScore = item.risk_score || 0;
    const riskColor = riskScore >= 80 ? "danger" : riskScore >= 40 ? "warning" : "success";

    const safeName = window.KpiValidation
      ? window.KpiValidation.sanitizeCorruptedText(item.name, "غير متاح")
      : (item.name || "غير متاح");
    const safeKindergarten = window.KpiValidation
      ? window.KpiValidation.sanitizeCorruptedText(item.kindergarten, "غير محدد")
      : (item.kindergarten || "غير محدد");
    const safeReason = window.KpiValidation
      ? window.KpiValidation.sanitizeCorruptedText(item.reason, "سبب غير محدد")
      : (item.reason || "سبب غير ممدد");

    li.innerHTML = `
             <div class="flex-grow-1">
                 <div class="d-flex align-items-center mb-1">
                     <span class="fw-bold text-dark me-2">${adminAnalyticsLiteral(safeName)}</span>
                     <small class="badge bg-${riskColor} text-white">${riskScore}% ${adminAnalyticsText("خطر", "risk")}</small>
                 </div>
                 <small class="text-muted d-block">${adminAnalyticsLiteral(safeKindergarten)}</small>
                 <div class="small text-danger mt-1">${adminAnalyticsLiteral(safeReason)}</div>
             </div>
             <div class="text-end">
                 <div class="progress" style="width: 60px; height: 6px;">
                     <div class="progress-bar bg-${riskColor}" style="width: ${riskScore}%"></div>
                 </div>
             </div>
         `;

    // Add click handler for drill-down
    li.style.cursor = "pointer";
    li.addEventListener("click", function () {
      if (item.kindergarten_id) {
        window.location.href = `/admin/analytics/drilldown/KINDERGARTEN/${item.kindergarten_id}`;
      }
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
             <td class="text-center" data-sort="${row.incident_rate}">${(row.incident_rate ?? 0).toFixed(2)}</td>
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

   topList.innerHTML = `<div class="list-group-item text-center text-muted small">${adminAnalyticsText("جاري التحميل...", "Loading...")}</div>`;
   lowList.innerHTML = `<div class="list-group-item text-center text-muted small">${adminAnalyticsText("جاري التحميل...", "Loading...")}</div>`;

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
   } catch (error) {
     console.error("Comparative analysis error:", error);
     topList.innerHTML = `<div class="list-group-item text-danger small">${adminAnalyticsText("تعذر تحميل التصنيفات.", "Unable to load rankings.")}</div>`;
     lowList.innerHTML = `<div class="list-group-item text-danger small">${adminAnalyticsText("تعذر تحميل التصنيفات.", "Unable to load rankings.")}</div>`;
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
       `ملاحظة: عدد الروضات المتاحة أقل من 5، لذا قد تظهر نفس الروضات في أكثر من قائمة.`,
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
                     <a href="/admin/analytics/drilldown/KINDERGARTEN/${item.kindergarten_id}" class="fw-bold text-dark text-decoration-none d-block" title="${adminAnalyticsText("انقر لعرض تفاصيل الروضة", "Click to view kindergarten details")}">
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

  safeSetText("countGreen", green);
  safeSetText("countAmber", amber);
  safeSetText("countRed", red);

  if (!adminAnalyticsHasChart()) {
    return;
  }

  if (governanceChart) governanceChart.destroy();

  governanceChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: [
        adminAnalyticsText("متميز", "Excellent"),
        adminAnalyticsText("متوسط", "Average"),
        adminAnalyticsText("يحتاج تحسين", "Needs improvement"),
      ],
      datasets: [
        {
          data: safeChartData([green, amber, red]),
          backgroundColor: ["#198754", "#ffc107", "#dc3545"],
          borderWidth: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
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
  container.innerHTML = `<div class="small text-muted">${adminAnalyticsText(`آخر تدريب: ${trainedAt} | الإصدار: ${version} | الثقة: ${confidence}`, `Last training: ${trainedAt} | Version: ${version} | Confidence: ${confidence}`)}</div>`;
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
  try {
    const res = await fetchWithAuth(`/api/analytics/alerts`);
    if (!res) return;
    const data = await res.json();
    const alertList = document.getElementById("alertList");
    const banner = document.getElementById("alertBanner");
    if (!alertList) return;
    alertList.innerHTML = "";
    const alerts = data.alerts || [];
    if (alerts.length) {
      banner.classList.remove("d-none");
      banner.textContent = adminAnalyticsText(
        `يوجد ${alerts.length} تنبيه نشط يتطلب المراجعة.`,
        `${alerts.length} active alerts require review.`
      );
    } else {
      banner.classList.add("d-none");
    }
    alerts.slice(0, 5).forEach((alert) => {
      const row = document.createElement("div");
      row.className = "list-group-item border-0";
      const severityClass = alert.severity === "CRITICAL" ? "bg-danger" :
                          alert.severity === "HIGH" ? "bg-warning text-dark" :
                          alert.severity === "MEDIUM" ? "bg-warning" : "bg-info text-dark";
      row.innerHTML = `<div class="d-flex justify-content-between">
        <div>
          <div class="fw-semibold">${escapeHtml(alert.message)}</div>
          <small class="text-muted">${formatMetricType(alert.metric_type)}</small>
        </div>
        <span class="badge ${severityClass}">${formatAnomalySeverity(alert.severity)}</span>
      </div>`;
      alertList.appendChild(row);
    });
  } catch (error) {
    console.error("Alerts load error", error);
  }
}

async function loadDataQuality() {
  try {
    const res = await fetchWithAuth(`/api/analytics/data-quality`);
    if (!res) return;
    const data = await res.json();
    const scoreEl = document.getElementById("dataQualityScore");
    const statusEl = document.getElementById("dataQualityStatus");
    if (scoreEl) scoreEl.textContent = `${(data.completeness_percent ?? 0).toFixed(1)}%`;
    if (statusEl)
      statusEl.textContent =
        (data.completeness_percent ?? 0) > 85
          ? adminAnalyticsText("ممتاز", "Excellent")
          : adminAnalyticsText("بحاجة تحسين", "Needs improvement");
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

  switch (metric) {
    case 'total_kg':
      return data.total_kindergartens_trend || [data.previous_period?.total_kindergartens, data.network_summary?.total_kindergartens];
    case 'total_children':
      return data.total_children_trend || [data.previous_period?.total_children, data.network_summary?.total_children];
    case 'attendance_rate':
      return data.attendance_rate_trend || [data.previous_period?.attendance_rate, data.network_summary?.attendance_rate];
    case 'incident_rate':
      return data.incident_rate_trend || [data.previous_period?.incident_rate, data.network_summary?.incident_rate];
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

window.addEventListener("languageChanged", () => {
  if (document.getElementById("periodStart") && document.getElementById("periodEnd")) {
    loadAdminAnalytics();
  }
});
