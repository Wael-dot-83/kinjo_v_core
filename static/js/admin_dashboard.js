/**
 * Admin Dashboard — KinJo v2.7
 * Handles KPI rendering, charts, activity feed, and alerts.
 * Depends on: chart_utils.js (safeChartData), admin_i18n.js (window.AdminI18n)
 * window.KINJO_LANG must be set before this script executes (injected by template).
 */

window.KINJO_LANG = window.KINJO_LANG || (document.documentElement.lang === 'en' ? 'en' : 'ar');

/** Safe HTML escaping for any string inserted via innerHTML */
function escapeHtml(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Enrollment enum → i18n key map ──────────────────────────────────────────
const ENROLLMENT_I18N = {
  ACTIVE:        "dashboard.enrollment_active",
  PENDING:       "dashboard.enrollment_pending",
  PENDING_REVIEW:"dashboard.enrollment_pending_review",
  SUBMITTED:     "dashboard.enrollment_submitted",
  ACCEPTED:      "dashboard.enrollment_accepted",
  REJECTED:      "dashboard.enrollment_rejected",
  WITHDRAWN:     "dashboard.enrollment_withdrawn",
  WAITLISTED:    "dashboard.enrollment_waitlisted",
  DRAFT:         "dashboard.enrollment_draft",
};

// Inline fallbacks — used only when JSON hasn't loaded yet
const ENROLLMENT_FALLBACK = {
  ar: {
    ACTIVE: "نشط", PENDING: "قيد الانتظار", PENDING_REVIEW: "قيد المراجعة",
    SUBMITTED: "مُقدَّم", ACCEPTED: "مقبول", REJECTED: "مرفوض",
    WITHDRAWN: "منسحب", WAITLISTED: "قائمة الانتظار", DRAFT: "مسودة",
  },
  en: {
    ACTIVE: "Active", PENDING: "Pending", PENDING_REVIEW: "Under Review",
    SUBMITTED: "Submitted", ACCEPTED: "Accepted", REJECTED: "Rejected",
    WITHDRAWN: "Withdrawn", WAITLISTED: "Waitlisted", DRAFT: "Draft",
  },
};

// KPI configuration — single source of truth, order determines render order
const KPI_CONFIG = [
  { key: "total_users",          icon: "bi bi-people-fill",       color: "primary", format: "number",     drilldown: "/admin/users",                     drilldownLabelKey: "dashboard.view_users" },
  { key: "active_users",         icon: "bi bi-person-check-fill", color: "success", format: "number",     drilldown: "/admin/users",                     drilldownLabelKey: "dashboard.view_users" },
  { key: "total_kindergartens",  icon: "bi bi-house-fill",        color: "info",    format: "number",     drilldown: "/admin/kg-overview",               drilldownLabelKey: "dashboard.view_kindergartens" },
  { key: "active_kindergartens", icon: "bi bi-house-check-fill",  color: "success", format: "number",     drilldown: "/admin/kg-overview",               drilldownLabelKey: "dashboard.view_kindergartens" },
  { key: "total_submissions",    icon: "bi bi-file-earmark-fill", color: "warning", format: "number",     drilldown: "/admin/analytics/daily-reports",   drilldownLabelKey: "dashboard.view_reports" },
  { key: "pending_submissions",  icon: "bi bi-clock-fill",        color: "danger",  format: "number",     drilldown: "/admin/analytics/daily-reports",   drilldownLabelKey: "dashboard.view_reports" },
  { key: "data_quality_score",   icon: "bi bi-graph-up-arrow",    color: "primary", format: "percentage", drilldown: "/admin/imported-kindergartens",    drilldownLabelKey: "dashboard.view_data_management" },
];

// English fallbacks for KPI labels (used if i18n JSON hasn't loaded yet)
const KPI_LABEL_FALLBACK = {
  total_users:          "Total Users",
  active_users:         "Active Users",
  total_kindergartens:  "Total Kindergartens",
  active_kindergartens: "Active Kindergartens",
  total_submissions:    "Total Submissions",
  pending_submissions:  "Pending Submissions",
  data_quality_score:   "Data Quality",
};

class AdminDashboard {
  constructor() {
    this.apiEndpoint     = "/api/admin/dashboard";
    this.refreshInterval = 300000; // 5 minutes
    this.intervalId      = null;
    this.charts          = {};
    this.isLoading       = false;
    this._listeners      = {};

    document.addEventListener("DOMContentLoaded", () => this.init());
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  init() {
    this.initEventListeners();
    this.initChartDefaults();
    this.loadDashboardData();
    // Auto-refresh existed unconditionally before (5-minute interval, no way
    // to disable); autoRefreshEnabled persists the user's choice to keep
    // that same default (on) when no preference has been saved yet.
    if (this.isAutoRefreshEnabled()) this.startAutoRefresh();
  }

  isAutoRefreshEnabled() {
    const stored = localStorage.getItem("autoRefreshEnabled");
    return stored === null ? true : stored === "true";
  }

  initEventListeners() {
    this._listeners.refresh    = () => this.loadDashboardData();
    this._listeners.retry      = () => this.loadDashboardData();
    this._listeners.visibility = () => {
      if (document.hidden) { this.stopAutoRefresh(); return; }
      if (this.isAutoRefreshEnabled()) this.startAutoRefresh();
    };
    this._listeners.autoRefreshToggle = (event) => {
      localStorage.setItem("autoRefreshEnabled", event.target.checked ? "true" : "false");
      if (event.target.checked) this.startAutoRefresh();
      else this.stopAutoRefresh();
    };

    document.getElementById("refresh-dashboard")?.addEventListener("click", this._listeners.refresh);
    document.getElementById("retry-dashboard")?.addEventListener("click",   this._listeners.retry);
    document.addEventListener("visibilitychange", this._listeners.visibility);

    const autoRefreshCheck = document.getElementById("autoRefreshCheck");
    if (autoRefreshCheck) {
      autoRefreshCheck.checked = this.isAutoRefreshEnabled();
      autoRefreshCheck.addEventListener("change", this._listeners.autoRefreshToggle);
    }
  }

  initChartDefaults() {
    if (typeof Chart === "undefined") return;
    Chart.defaults.responsive          = true;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.display  = true;
    Chart.defaults.plugins.legend.position = "bottom";
  }

  // ── State Machine ─────────────────────────────────────────────────────────
  // Visibility is controlled solely via data-ui-state on #admin-dashboard.
  // CSS in admin_design_system.css translates state → display for each panel.
  // Valid states: "loading" | "success" | "error"

  setState(state) {
    const container = document.getElementById("admin-dashboard");
    if (container) container.dataset.uiState = state;
  }

  // ── Data Loading ──────────────────────────────────────────────────────────

  async loadDashboardData() {
    if (this.isLoading) return;
    this.isLoading = true;
    this.setState("loading");

    const refreshBtn = document.getElementById("refresh-dashboard");
    const refreshText = refreshBtn?.querySelector(".refresh-text");
    const refreshIcon = refreshBtn?.querySelector(".refresh-icon");
    const lastUpdatedLabel = document.getElementById("last-updated-time");
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.classList.add("is-loading");
      refreshBtn.classList.remove("is-success");
      if (refreshText) refreshText.textContent = lang === "en" ? "Updating data..." : "جاري تحديث البيانات...";
      if (refreshIcon) refreshIcon.classList.add("spin");
    }

    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), 8000);

    try {
      const response = await fetch(this.apiEndpoint, {
        method: "GET",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      this._lastData = data;
      this.renderDashboard(data);
      this.setState("success");
      this._waitForI18nThenRefresh();

      if (refreshBtn) {
        refreshBtn.classList.remove("is-loading");
        refreshBtn.classList.add("is-success");
        if (refreshText) refreshText.textContent = lang === "en" ? "Update Successful" : "تم التحديث بنجاح";
        if (refreshIcon) {
            refreshIcon.classList.remove("spin", "bi-arrow-clockwise");
            refreshIcon.classList.add("bi-check2");
        }
        
        const now = new Date();
        const timeStr = now.toLocaleTimeString(lang === "en" ? "en-US" : "ar-SA", { hour: '2-digit', minute: '2-digit' });
        if (lastUpdatedLabel) {
            lastUpdatedLabel.textContent = lang === "en" ? `Last updated: ${timeStr}` : `آخر تحديث: ${timeStr}`;
        }

        setTimeout(() => {
          refreshBtn.disabled = false;
          refreshBtn.classList.remove("is-success");
          if (refreshText) refreshText.textContent = lang === "en" ? "Update Data" : "تحديث البيانات";
          if (refreshIcon) {
            refreshIcon.classList.add("bi-arrow-clockwise");
            refreshIcon.classList.remove("bi-check2");
          }
        }, 2000);
      }
    } catch (error) {
      clearTimeout(timeoutId);
      console.error("[AdminDashboard] load error:", error);
      const isTimeout = error.name === "AbortError";
      this._setErrorMessage(this.t(
        isTimeout ? "errors.request_timeout" : "errors.generic_error",
        isTimeout ? "Request timed out. Please try again." : "An error occurred. Please try again."
      ));
      this.setState("error");

      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.classList.remove("is-loading");
        if (refreshText) refreshText.textContent = lang === "en" ? "Update Data" : "تحديث البيانات";
        if (refreshIcon) refreshIcon.classList.remove("spin");
      }
    } finally {
      this.isLoading = false;
    }
  }

  _setErrorMessage(message) {
    const el = document.getElementById("error-message");
    if (el) el.textContent = message;
  }

  // Under heavy load the async translation JSON can still be loading when this
  // first render happens, leaving KPI trend/status/drilldown and activity-meta
  // text stuck on their (English) fallback. Poll for the loaded-from-files flag, bounded,
  // and re-render exactly once when translations land — never again after
  // that, so later user-driven refreshes don't get needlessly re-rendered.
  _waitForI18nThenRefresh(attemptsLeft = 20) {
    if (this._i18nRefreshed) return;
    const canary = window.AdminI18n?.loadedFromFiles;
    if (canary) {
      this._i18nRefreshed = true;
      if (this._lastData) this.renderDashboard(this._lastData);
      return;
    }
    if (attemptsLeft <= 0) return;
    setTimeout(() => this._waitForI18nThenRefresh(attemptsLeft - 1), 100);
  }

  // ── Rendering ─────────────────────────────────────────────────────────────

  renderDashboard(data) {
    const normalized = this.normalizePayload(data || {});
    this.renderKPICards(normalized.kpis, normalized.kpi_trends, normalized.data_quality_reasons);
    this.renderCharts(normalized.charts);
    // Skip when an ActivityFilterBar owns #activity-feed (admin_activity_filters.js):
    // both scripts render into the same container on admin_dashboard.html, and
    // this unfiltered/unpaginated top-10 payload used to win the race on every
    // load AND on every 5-minute auto-refresh, silently discarding any filter
    // or page the user had applied while the pagination footer below it (which
    // only ActivityFilterBar updates) kept claiming the filtered view was
    // still active. ActivityFilterBar.load() is this container's sole owner
    // whenever it's present; renderActivityFeed remains here as the shared
    // rendering primitive it calls into (window.adminDashboard.renderActivityFeed).
    if (!document.getElementById("activity-filter-bar")) {
      this.renderActivityFeed(normalized.recent_activity);
    }
    this.renderAlerts(normalized.alerts);
    this.renderExecutiveSections(normalized);
    // Translate any data-i18n elements injected dynamically by this script
    window.AdminI18n?.translatePage?.();
  }

  /**
   * Map API response shape to internal normalized form.
   * The API returns { kpis, summary, system_overview, charts, alerts, recent_activity }.
   */
  normalizePayload(data) {
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    const lang   = window.KINJO_LANG === "en" ? "en" : "ar";

    // kpis is now a flat dict provided directly by the API
    const kpis = data.kpis || {};
    const kpiTrends = data.kpi_trends || {};
    const dataQualityReasons = Array.isArray(data.data_quality_reasons) ? data.data_quality_reasons : [];

    const chartPayload      = data.charts || {};
    const userActivityChart = {
      labels: Array.isArray(chartPayload.attendance) ? chartPayload.attendance.map((i) => i.date)              : [],
      values: Array.isArray(chartPayload.attendance) ? chartPayload.attendance.map((i) => this.toNumber(i.value)) : [],
    };

    const enrollment      = chartPayload.enrollment || {};
    const submissionChart = {
      labels: Object.keys(enrollment).map((k) => {
        const i18nKey  = ENROLLMENT_I18N[k];
        const fallback = (ENROLLMENT_FALLBACK[lang] || ENROLLMENT_FALLBACK.en)[k] || k;
        return i18nKey ? this.t(i18nKey, fallback) : fallback;
      }),
      values: Object.values(enrollment).map((v) => this.toNumber(v)),
    };

    const recentActivity = Array.isArray(data.recent_activity) && data.recent_activity.length > 0
      ? data.recent_activity
      : [];

    return {
      kpis,
      kpi_trends: kpiTrends,
      data_quality_reasons: dataQualityReasons,
      charts: { user_activity: userActivityChart, data_submissions: submissionChart },
      recent_activity: recentActivity,
      alerts,
      system_overview: data.system_overview || {},
      summary: data.summary || {},
      generated_at: data.generated_at || null,
    };
  }

  // ── KPI Cards ─────────────────────────────────────────────────────────────

  renderKPICards(kpis, kpiTrends, dataQualityReasons) {
    const container = document.getElementById("kpi-cards");
    if (!container) return;
    container.innerHTML = "";
    // Always render all KPI slots — sanitizeKPIValue returns null for invalid/missing values,
    // which formatKPIValue renders as "—" to preserve layout integrity.
    KPI_CONFIG.forEach((config) => {
      container.appendChild(this.createKPICard(
        config,
        this.sanitizeKPIValue(config.key, kpis[config.key]),
        (kpiTrends || {})[config.key],
        config.key === "data_quality_score" ? (dataQualityReasons || []) : null
      ));
    });
  }

  // Returns null for invalid or negative values (renders as "—"), clamped value otherwise.
  sanitizeKPIValue(key, raw) {
    const num = Number(raw);
    if (!Number.isFinite(num) || num < 0) return null;
    if (key === "data_quality_score") return Math.min(100, Math.max(0, num));
    return num;
  }

  createKPICard(config, value, trendMeta, dataQualityReasons) {
    // <li>, not <div>: #kpi-cards is a <ul> so screen readers can enumerate
    // the collection (USWDS card component). No role="region"/aria-label
    // here anymore — the card now carries a real heading (see titleEl
    // below), which is the correct accessible name source for a list item.
    const card = document.createElement("li");
    card.className = "admin-kpi-card";

    const { formattedValue, badgeHtml } = this.formatKPIValue(config, value);

    // Icon
    const iconDiv = document.createElement("div");
    iconDiv.className = `admin-kpi-card-icon admin-kpi-card-${config.color}`;
    const iconEl = document.createElement("i");
    iconEl.className = config.icon;
    iconEl.setAttribute("aria-hidden", "true");
    iconDiv.appendChild(iconEl);

    // Content
    const contentDiv = document.createElement("div");
    contentDiv.className = "admin-kpi-card-content";

    const valueDiv = document.createElement("div");
    valueDiv.className = "admin-kpi-card-value";
    valueDiv.textContent = formattedValue;
    contentDiv.appendChild(valueDiv);

    if (badgeHtml) {
      const badgeWrap = document.createElement("div");
      badgeWrap.innerHTML = badgeHtml; // content produced by escapeHtml — safe
      contentDiv.appendChild(badgeWrap);
    }

    // <h3>, not <div>: a real heading gives the card an accessible name and
    // keeps it in logical outline order (USWDS card component) — every
    // sibling card on this page (Alerts, Charts, Activity, Quick Actions)
    // already titles itself with <h3 class="admin-card-title">.
    const titleEl = document.createElement("h3");
    titleEl.className = "admin-kpi-card-title";
    titleEl.setAttribute("data-i18n", `dashboard.${config.key}`);
    titleEl.textContent = this.t(`dashboard.${config.key}`, KPI_LABEL_FALLBACK[config.key] || config.key);
    contentDiv.appendChild(titleEl);

    if (trendMeta && value !== null) {
      contentDiv.appendChild(this.createKPITrendRow(trendMeta));
      contentDiv.appendChild(this.createKPIStatusRow(trendMeta));
    }

    if (Array.isArray(dataQualityReasons) && dataQualityReasons.length > 0) {
      contentDiv.appendChild(this.createDataQualityReasons(dataQualityReasons));
    }

    if (config.drilldown) {
      contentDiv.appendChild(this.createKPIDrilldownLink(config));
    }

    card.appendChild(iconDiv);
    card.appendChild(contentDiv);
    return card;
  }

  // Trend row: icon (shape, not just color) + comparison-to-previous-period text.
  createKPITrendRow(trendMeta) {
    const row = document.createElement("div");
    row.className = `admin-kpi-card-trend admin-kpi-card-trend--${trendMeta.trend || "flat"}`;

    const icon = document.createElement("i");
    // Up/down are vertical arrows — direction is unaffected by RTL/LTR, so no .icon-directional here.
    icon.className =
      trendMeta.trend === "up"   ? "bi bi-arrow-up-short" :
      trendMeta.trend === "down" ? "bi bi-arrow-down-short" :
      "bi bi-dash-lg";
    icon.setAttribute("aria-hidden", "true");
    row.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = this.formatTrendComparison(trendMeta);
    row.appendChild(text);

    return row;
  }

  formatTrendComparison(trendMeta) {
    const locale = window.KINJO_LANG === "ar" ? "ar-JO" : "en-US";
    const sign = trendMeta.trend === "up" ? "+" : trendMeta.trend === "down" ? "-" : "";
    let changeText;
    if (trendMeta.change_pct !== null && trendMeta.change_pct !== undefined) {
      changeText = sign + new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(Math.abs(trendMeta.change_pct)) + "%";
    } else {
      changeText = sign + new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(Math.abs(trendMeta.change || 0));
    }
    return this.t("dashboard.trend_compare_period", `${changeText} vs. previous period`, { change: changeText });
  }

  // Status meaning — icon + text, never color alone.
  createKPIStatusRow(trendMeta) {
    const row = document.createElement("div");
    row.className = `admin-kpi-card-status admin-kpi-card-status--${trendMeta.status || "good"}`;

    const icon = document.createElement("i");
    icon.className = trendMeta.status === "warning" ? "bi bi-exclamation-triangle-fill" : "bi bi-check-circle-fill";
    icon.setAttribute("aria-hidden", "true");
    row.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = trendMeta.status === "warning"
      ? this.t("dashboard.status_warning", "Needs attention")
      : this.t("dashboard.status_good", "Good");
    row.appendChild(text);

    return row;
  }

  // Data Quality card only: reasons behind the score, in a native <details> disclosure (free keyboard support).
  createDataQualityReasons(reasons) {
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    const details = document.createElement("details");
    details.className = "admin-kpi-dq-reasons";

    const summary = document.createElement("summary");
    summary.textContent = this.t("dashboard.dq_view_issues", "View data issues");
    details.appendChild(summary);

    const list = document.createElement("ul");
    list.className = "admin-kpi-dq-reasons-list";
    reasons.forEach((reason) => {
      const li = document.createElement("li");
      li.setAttribute("dir", "auto");
      li.textContent = reason[`label_${lang}`] || reason.label_ar || "";
      list.appendChild(li);
    });
    details.appendChild(list);

    const improveLink = document.createElement("a");
    improveLink.className = "admin-kpi-dq-improve-link";
    improveLink.href = "/admin/imported-kindergartens";
    improveLink.textContent = this.t("dashboard.dq_improve", "Improve data quality");
    details.appendChild(improveLink);

    return details;
  }

  createKPIDrilldownLink(config) {
    const link = document.createElement("a");
    link.className = "admin-kpi-card-drilldown";
    link.href = config.drilldown;

    const text = document.createElement("span");
    text.textContent = this.t(config.drilldownLabelKey, KPI_LABEL_FALLBACK[config.key] || "View details");
    link.appendChild(text);

    const chevron = document.createElement("i");
    chevron.className = "bi bi-chevron-right icon icon-directional";
    chevron.setAttribute("aria-hidden", "true");
    link.appendChild(chevron);

    return link;
  }

  formatKPIValue(config, value) {
    // Null signals "data unavailable" — show em-dash instead of zero
    if (value === null || value === undefined) return { formattedValue: "—", badgeHtml: "" };

    const locale       = window.KINJO_LANG === "ar" ? "ar-JO" : "en-US";
    let formattedValue = String(value);
    let badgeHtml      = "";

    if (config.format === "number") {
      formattedValue = new Intl.NumberFormat(locale).format(value);
    } else if (config.format === "percentage") {
      formattedValue = new Intl.NumberFormat(locale, { style: "percent", maximumFractionDigits: 1 }).format(value / 100);
      if (config.key === "data_quality_score") {
        const { cls, key, fb } = value >= 80
          ? { cls: "dq-badge-good",    key: "dashboard.dq_good",    fb: "Good" }
          : value >= 60
          ? { cls: "dq-badge-average", key: "dashboard.dq_average", fb: "Average" }
          : { cls: "dq-badge-low",     key: "dashboard.dq_low",     fb: "Low" };
        badgeHtml = `<span class="dq-badge ${escapeHtml(cls)}">${escapeHtml(this.t(key, fb))}</span>`;
      }
    }

    return { formattedValue, badgeHtml };
  }

  // ── Charts ────────────────────────────────────────────────────────────────

  renderCharts(charts) {
    if (typeof Chart === "undefined") return;
    if (charts.user_activity)    this.renderUserActivityChart(charts.user_activity);
    if (charts.data_submissions) this.renderSubmissionsChart(charts.data_submissions);
  }

  renderUserActivityChart(data) {
    const ctx = document.getElementById("user-activity-chart");
    if (!ctx) return;
    this.charts.userActivity?.destroy();
    const context = ctx.getContext("2d");
    const gradient = context ? (() => {
      const g = context.createLinearGradient(0, 0, 0, 220);
      g.addColorStop(0, "rgba(31, 94, 71, 0.28)");
      g.addColorStop(1, "rgba(31, 94, 71, 0.02)");
      return g;
    })() : "rgba(31, 94, 71, 0.1)";
    this.charts.userActivity = new Chart(ctx, {
      type: "line",
      data: {
        labels:   safeChartData(data.labels),
        datasets: [{
          label:                this.t("dashboard.active_users", "Active Users"),
          data:                 safeChartData(data.values),
          borderColor:          "#4F46E5",
          backgroundColor:      gradient,
          tension:              0.4,
          fill:                 true,
          pointRadius:          4,
          pointHoverRadius:     6,
          pointBackgroundColor: "#4F46E5",
          pointBorderColor:     "#fff",
          pointBorderWidth:     2,
          borderWidth:          2.5,
        }],
      },
      options: {
        animation: { duration: 600, easing: "easeOutQuart" },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f8fafc",
            bodyColor:  "#f8fafc",
            padding:    10,
            cornerRadius: 8,
          },
        },
        scales: {
          x: { ticks: { color: "#6c757d" }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0, color: "#6c757d" }, grid: { color: "rgba(0,0,0,0.06)" } },
        },
      },
    });
  }

  renderSubmissionsChart(data) {
    const ctx = document.getElementById("enrollment-status-chart");
    if (!ctx) return;
    this.charts.dataSubmissions?.destroy();
    const palette = ["#0d6efd", "#198754", "#ffc107", "#dc3545", "#6c757d", "#0dcaf0"];
    this.charts.dataSubmissions = new Chart(ctx, {
      type: "bar",
      data: {
        labels:   safeChartData(data.labels),
        datasets: [{
          label:           this.t("dashboard.enrollment_status", "Enrollment Status"),
          data:            safeChartData(data.values),
          backgroundColor: safeChartData(data.labels).map((_, i) => palette[i % palette.length]),
          borderWidth:     0,
          borderRadius:    6,
        }],
      },
      options: {
        indexAxis: "y",
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f8fafc",
            bodyColor:  "#f8fafc",
            padding:    10,
            cornerRadius: 8,
            callbacks: {
              label: (ctx) => ` ${ctx.parsed.x.toLocaleString()}`,
            },
          },
        },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: "rgba(0,0,0,0.06)" } },
          y: { ticks: { color: "#495057" }, grid: { display: false } },
        },
      },
    });
  }

  // ── Activity Feed ─────────────────────────────────────────────────────────

  renderActivityFeed(activities) {
    const container = document.getElementById("activity-feed");
    if (!container) return;
    container.innerHTML = "";

    if (!activities || activities.length === 0) {
      container.appendChild(this.createEmptyState(
        "dashboard.no_recent_activity", "No recent activity",
        "dashboard.no_activity_hint",   "Add users or monitor operations to see activity here",
        "bi-clock-history",
        "dashboard.manage_users", "Manage Users", "/admin/users"
      ));
      return;
    }
    activities.forEach((a) => container.appendChild(this.createActivityItem(a)));
  }

  createActivityItem(activity) {
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    let message = activity[`message_${lang}`] || activity.message || "";

    // Elevate low-value repetitive messages to professional event titles.
    // Gated on status === "success": the substring check alone also matches
    // LOGIN_FAILED's message ("Failed login attempt" / "محاولة تسجيل دخول
    // فاشلة", both contain "login"/"تسجيل دخول"), which silently relabeled
    // failed login attempts as "Successful Authentication" while the status
    // badge next to it still correctly said "Failed" — hiding a
    // security-relevant signal behind a contradictory, success-sounding title.
    if (
      activity.status === "success" &&
      (message.includes("تسجيل دخول") || message.includes("User login") || message.includes("login"))
    ) {
      message = lang === "en" ? "Successful Authentication" : "دخول ناجح";
    }

    const article = document.createElement("article");
    article.className = "executive-activity-item";
    article.setAttribute("role", "listitem");

    // Title Row
    const titleRow = document.createElement("div");
    titleRow.className = "activity-title-row";
    
    const title = document.createElement("h4");
    title.className = "activity-event-title";
    title.textContent = message;

    const badge = document.createElement("span");
    const statusClass = activity.status || "success";
    badge.className = `activity-status-badge badge-${statusClass}`;
    badge.textContent = this.formatStatus(activity.status) || (lang === "en" ? "Success" : "مكتمل");

    titleRow.appendChild(title);
    titleRow.appendChild(badge);

    // Meta Row
    const metaRow = document.createElement("div");
    metaRow.className = "activity-meta-row";

    const actor = document.createElement("span");
    actor.className = "activity-actor";
    actor.innerHTML = `<i class="bi bi-person-fill"></i> ${activity.user_name || this.t("dashboard.system_actor", "System")}`;

    const time = document.createElement("span");
    time.className = "activity-time";
    time.innerHTML = `<i class="bi bi-clock"></i> ${this.formatTimeAgo(activity.timestamp)}`;

    metaRow.appendChild(actor);
    metaRow.appendChild(time);

    article.appendChild(titleRow);
    article.appendChild(metaRow);

    // Optional Category
    const moduleName = lang === "en" ? activity.module_en : activity.module_ar;
    if (moduleName) {
      const categoryRow = document.createElement("div");
      categoryRow.className = "activity-category-row";
      categoryRow.innerHTML = `<span class="activity-category-badge"><i class="bi bi-folder2"></i> ${moduleName}</span>`;
      article.appendChild(categoryRow);
    }

    return article;
  }

  formatRole(role) {
    if (!role) return "";
    return this.t(`users.${String(role).toLowerCase()}`, role);
  }

  formatStatus(status) {
    if (!status) return "";
    return this.t(`dashboard.status_${status}`, status);
  }

  formatSeverity(severity) {
    if (!severity) return "";
    return this.t(`dashboard.severity_${severity}`, severity);
  }

  // ── Alerts ────────────────────────────────────────────────────────────────

  renderAlerts(alerts) {
    const container = document.getElementById("alerts-list");
    if (!container) return;
    container.innerHTML = "";

    if (!alerts || alerts.length === 0) {
      container.appendChild(this.createEmptyState(
        "dashboard.no_alerts",      "No active alerts",
        "dashboard.no_alerts_hint", "You'll be notified when important system events occur",
        "bi-bell-slash"
      ));
      return;
    }
    alerts.forEach((a) => container.appendChild(this.createAlertItem(a)));
  }

  createAlertItem(alert) {
    const lang    = window.KINJO_LANG === "en" ? "en" : "ar";
    const message = alert[`message_${lang}`] || alert.message || "";
    return this._createFeedItem({
      wrapperClass:  `admin-alert-item admin-alert-${alert.severity || "info"}`,
      iconWrapClass: "admin-alert-icon",
      iconClass:     this.getAlertIcon(alert.severity),
      contentClass:  "admin-alert-content",
      msgClass:      "admin-alert-message",
      timeClass:     "admin-alert-time",
      message,
      timestamp:     alert.timestamp,
      role:          "listitem",
    });
  }

  // Shared DOM builder for activity and alert feed items — eliminates duplication.
  _createFeedItem({ wrapperClass, iconWrapClass, iconClass, contentClass, msgClass, timeClass, message, timestamp, role }) {
    const item = document.createElement("div");
    item.className = wrapperClass;
    if (role) item.setAttribute("role", role);

    const iconDiv = document.createElement("div");
    iconDiv.className = iconWrapClass;
    const icon = document.createElement("i");
    icon.className = iconClass;
    icon.setAttribute("aria-hidden", "true");
    iconDiv.appendChild(icon);

    const contentDiv = document.createElement("div");
    contentDiv.className = contentClass;

    const msgDiv = document.createElement("div");
    msgDiv.className = msgClass;
    msgDiv.textContent = message || "";

    const timeDiv = document.createElement("div");
    timeDiv.className = timeClass;
    timeDiv.textContent = this.formatTimeAgo(timestamp);

    contentDiv.appendChild(msgDiv);
    contentDiv.appendChild(timeDiv);
    item.appendChild(iconDiv);
    item.appendChild(contentDiv);
    return item;
  }

  // ── Empty State ───────────────────────────────────────────────────────────

  createEmptyState(primaryKey, primaryFallback, hintKey, hintFallback, iconClass = "bi-inbox", ctaKey = null, ctaFallback = null, ctaHref = null) {
    const wrapper = document.createElement("div");
    wrapper.className = "admin-empty-state";

    const iconEl = document.createElement("i");
    iconEl.className = `bi ${iconClass} admin-empty-state-icon`;
    iconEl.setAttribute("aria-hidden", "true");
    wrapper.appendChild(iconEl);

    const p = document.createElement("p");
    p.className = "admin-no-data";
    p.setAttribute("data-i18n", primaryKey);
    p.textContent = this.t(primaryKey, primaryFallback);

    const hint = document.createElement("p");
    hint.className = "admin-no-data-hint";
    hint.setAttribute("data-i18n", hintKey);
    hint.textContent = this.t(hintKey, hintFallback);

    wrapper.appendChild(p);
    wrapper.appendChild(hint);

    if (ctaKey && ctaHref) {
      const cta = document.createElement("a");
      cta.className = "admin-btn admin-btn-primary admin-empty-state-cta";
      cta.href = ctaHref;
      cta.setAttribute("data-i18n", ctaKey);
      cta.textContent = this.t(ctaKey, ctaFallback || ctaKey);
      wrapper.appendChild(cta);
    }

    return wrapper;
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  formatNumber(num) {
    const locale = window.KINJO_LANG === "ar" ? "ar-JO" : "en-US";
    return new Intl.NumberFormat(locale).format(num);
  }

  toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  formatTimeAgo(timestamp) {
    if (!timestamp) return "";
    const time = new Date(timestamp);
    if (isNaN(time.getTime())) return "";
    const diff    = Math.max(0, Date.now() - time.getTime());
    const minutes = Math.floor(diff / 60000);
    const hours   = Math.floor(diff / 3600000);
    const days    = Math.floor(diff / 86400000);
    if (minutes < 1)  return this.t("common.just_now", "just now");
    if (minutes < 60) return this.t("dashboard.time_minutes_ago", `${minutes} minutes ago`, { count: this.formatNumber(minutes) });
    if (hours   < 24) return this.t("dashboard.time_hours_ago",   `${hours} hours ago`,     { count: this.formatNumber(hours) });
    return this.t("dashboard.time_days_ago", `${days} days ago`, { count: this.formatNumber(days) });
  }

  t(key, fallback = "", params = {}) {
    const i18n = window.AdminI18n;
    if (i18n && typeof i18n.translate === "function") return i18n.translate(key, fallback, params);
    return fallback || key;
  }

  getActivityIcon(type) {
    return {
      user_login:    "bi bi-box-arrow-in-right",
      user_logout:   "bi bi-box-arrow-left",
      data_submit:   "bi bi-upload",
      user_create:   "bi bi-person-plus-fill",
      system_update: "bi bi-gear-fill",
    }[type] || "bi bi-info-circle-fill";
  }

  getAlertIcon(severity) {
    // get_admin_dashboard's alert builders emit severity="error" (expired
    // licenses, >5 incidents/week) — this map had no "error" key at all, so
    // those alerts silently fell through to the generic info-circle icon
    // instead of a severity-appropriate one.
    return {
      critical: "bi bi-exclamation-triangle-fill",
      error:    "bi bi-exclamation-triangle-fill",
      warning:  "bi bi-exclamation-circle-fill",
      info:     "bi bi-info-circle-fill",
      success:  "bi bi-check-circle-fill",
    }[severity] || "bi bi-info-circle-fill";
  }

  // ── Auto Refresh ──────────────────────────────────────────────────────────

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.intervalId = setInterval(() => this.loadDashboardData(), this.refreshInterval);
  }

  stopAutoRefresh() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  // ── Executive decision-support sections (real backend data only) ──────

  renderExecutiveSections(norm) {
    this.renderSystemStatus(norm);
    this.renderExecutiveSummary(norm);
    this.renderRequestPipeline(norm);
    this.renderDataQualityCenter(norm);
  }

  _statusFromThresholds(value, warn, critical) {
    if (value == null) return "unavailable";
    if (value >= critical) return "good";
    if (value >= warn) return "warning";
    return "critical";
  }

  _statusBadge(status, labelAr) {
    const span = document.createElement("span");
    span.className = "admin-status-badge admin-status--" + (status || "info");
    span.textContent = labelAr;
    return span;
  }

  _statChip(label, value, hint) {
    const chip = document.createElement("div");
    chip.className = "admin-status-chip";
    const v = document.createElement("strong");
    v.className = "admin-status-chip-value";
    v.textContent = value == null ? "—" : String(value);
    const l = document.createElement("span");
    l.className = "admin-status-chip-label";
    l.textContent = label;
    chip.append(v, l);
    if (hint) {
      const h = document.createElement("span");
      h.className = "admin-status-chip-hint";
      h.textContent = hint;
      chip.appendChild(h);
    }
    return chip;
  }

  renderSystemStatus(norm) {
    const el = document.getElementById("system-status-banner");
    if (!el) return;
    const body = el.querySelector(".admin-card-body");
    if (!body) return;
    body.innerHTML = "";
    const so = norm.system_overview || {};
    const sum = norm.summary || {};
    const grid = document.createElement("div");
    grid.className = "admin-status-chip-grid";
    grid.append(
      this._statChip(this.t("dashboard.total_kindergartens", "Kindergartens"), so.total_kindergartens),
      this._statChip(this.t("dashboard.active_kindergartens", "Active kindergartens"), so.active_kindergartens),
      this._statChip(this.t("dashboard.total_users", "Users"), so.total_users),
      this._statChip(this.t("dashboard.pending_applications", "Pending applications"), sum.pending_applications),
      this._statChip(this.t("dashboard.pending_daily_reports", "Pending reports"), sum.pending_daily_reports),
      this._statChip(this.t("dashboard.recent_incidents", "Incidents (7d)"), sum.recent_incidents),
      this._statChip(this.t("dashboard.attendance_rate", "Attendance rate"), (sum.attendance_rate != null ? sum.attendance_rate + "%" : null)),
    );
    body.appendChild(grid);
    if (norm.generated_at) {
      const fresh = document.createElement("p");
      fresh.className = "admin-status-freshness";
      fresh.textContent = (window.KINJO_LANG === "en" ? "Data as of " : "البيانات حتى ") + norm.generated_at;
      body.appendChild(fresh);
    }
  }

  renderExecutiveSummary(norm) {
    const el = document.getElementById("executive-summary");
    if (!el) return;
    const body = el.querySelector(".admin-card-body");
    if (!body) return;
    body.innerHTML = "";
    const so = norm.system_overview || {};
    const sum = norm.summary || {};
    const kpis = norm.kpis || {};
    const dq = kpis.data_quality_score;
    const serviceAvail = (so.total_kindergartens ? Math.round((so.active_kindergartens / so.total_kindergartens) * 100) : null);
    const items = [
      {
        label: this.t("dashboard.system_health", "System health"),
        value: sum.attendance_rate != null ? sum.attendance_rate + "%" : null,
        status: this._statusFromThresholds(sum.attendance_rate, 60, 80),
        explain: this.t("dashboard.system_health_explain", "Today's attendance rate across active kindergartens."),
        action: this.t("dashboard.review_operations", "Review operations"),
        href: "/admin/kg-overview",
      },
      {
        label: this.t("dashboard.data_quality", "Data quality"),
        value: dq != null ? dq + "%" : null,
        status: this._statusFromThresholds(dq, 60, 80),
        explain: this.t("dashboard.data_quality_explain", "Share of active kindergartens that reported in the last 7 days."),
        action: this.t("dashboard.improve_data", "Improve data"),
        href: "/admin/imported-kindergartens",
      },
      {
        label: this.t("dashboard.security_index", "Security index"),
        value: null,
        status: "info",
        explain: this.t("dashboard.security_explain", "Review the audit log and active alerts for security posture."),
        action: this.t("dashboard.review_audit", "Review audit log"),
        href: "/admin/audit-logs",
      },
      {
        label: this.t("dashboard.service_availability", "Service availability"),
        value: serviceAvail != null ? serviceAvail + "%" : null,
        status: this._statusFromThresholds(serviceAvail, 90, 100),
        explain: this.t("dashboard.service_availability_explain", "Active kindergartens as a share of all registered kindergartens."),
        action: this.t("dashboard.review_kindergartens", "Review kindergartens"),
        href: "/admin/kindergartens",
      },
      {
        label: this.t("dashboard.pending_requests", "Pending requests"),
        value: sum.pending_applications,
        status: (sum.pending_applications || 0) > 0 ? "warning" : "good",
        explain: this.t("dashboard.pending_requests_explain", "Enrollment applications awaiting review."),
        action: this.t("dashboard.review_requests", "Review requests"),
        href: "/admin/analytics",
      },
      {
        label: this.t("dashboard.user_activity", "User activity"),
        value: so.total_users,
        status: "info",
        explain: this.t("dashboard.user_activity_explain", "Total registered platform users."),
        action: this.t("dashboard.manage_users", "Manage users"),
        href: "/admin/users",
      },
    ];
    const list = document.createElement("ul");
    list.className = "admin-exec-summary-list";
    list.setAttribute("role", "list");
    const labels = { good: this.t("dashboard.status_good", "Healthy"), warning: this.t("dashboard.status_warning", "Warning"), critical: this.t("dashboard.status_critical", "Critical"), info: this.t("dashboard.status_info", "Info"), unavailable: this.t("dashboard.status_unavailable", "Unavailable") };
    items.forEach((it) => {
      const li = document.createElement("li");
      li.className = "admin-exec-summary-item";
      li.setAttribute("role", "listitem");
      const head = document.createElement("div");
      head.className = "admin-exec-summary-head";
      const name = document.createElement("span");
      name.className = "admin-exec-summary-name";
      name.textContent = it.label;
      head.append(name, this._statusBadge(it.status, labels[it.status] || it.status));
      const val = document.createElement("div");
      val.className = "admin-exec-summary-value";
      val.textContent = it.value == null ? this.t("dashboard.not_available", "Not available") : String(it.value);
      const exp = document.createElement("p");
      exp.className = "admin-exec-summary-explain";
      exp.textContent = it.explain;
      const act = document.createElement("a");
      act.className = "admin-exec-summary-action";
      act.href = it.href;
      act.textContent = it.action;
      li.append(head, val, exp, act);
      list.appendChild(li);
    });
    body.appendChild(list);
  }

  renderRequestPipeline(norm) {
    const el = document.getElementById("request-pipeline");
    if (!el) return;
    const body = document.getElementById("request-pipeline-body");
    if (!body) return;
    body.innerHTML = "";
    const sum = norm.summary || {};
    const pending = sum.pending_applications || 0;
    const pendingReports = sum.pending_daily_reports || 0;

    const wrap = document.createElement("div");
    wrap.className = "admin-pipeline";

    const stages = [
      this.t("dashboard.pipe_new", "New"),
      this.t("dashboard.pipe_submitted", "Submitted"),
      this.t("dashboard.pipe_review", "Under Review"),
      this.t("dashboard.pipe_documents", "Waiting Documents"),
      this.t("dashboard.pipe_approved", "Approved"),
      this.t("dashboard.pipe_rejected", "Rejected"),
    ];
    const row = document.createElement("ol");
    row.className = "admin-pipeline-stages";
    row.setAttribute("role", "list");
    stages.forEach((st, i) => {
      const li = document.createElement("li");
      li.className = "admin-pipeline-stage";
      li.setAttribute("role", "listitem");
      if (stages[i] === this.t("dashboard.pipe_review", "Under Review")) li.classList.add("is-current");
      const span = document.createElement("span");
      span.textContent = st;
      li.appendChild(span);
      row.appendChild(li);
    });
    wrap.appendChild(row);

    const meta = document.createElement("div");
    meta.className = "admin-pipeline-meta";
    meta.append(
      this._statChip(this.t("dashboard.pending_review", "Pending review"), pending),
      this._statChip(this.t("dashboard.pending_reports", "Pending reports"), pendingReports),
    );
    wrap.appendChild(meta);

    const cta = document.createElement("a");
    cta.className = "admin-btn admin-btn-primary";
    cta.href = "/admin/analytics";
    cta.textContent = this.t("dashboard.review_pending_requests", "Review pending requests");
    wrap.appendChild(cta);

    body.appendChild(wrap);
  }

  renderDataQualityCenter(norm) {
    const el = document.getElementById("data-quality-center");
    if (!el) return;
    const body = document.getElementById("data-quality-body");
    if (!body) return;
    body.innerHTML = "";
    const dq = (norm.kpis || {}).data_quality_score;
    const reasons = norm.data_quality_reasons || [];

    const scoreWrap = document.createElement("div");
    scoreWrap.className = "admin-dq-center";
    const scoreLabel = document.createElement("div");
    scoreLabel.className = "admin-dq-center-label";
    scoreLabel.textContent = this.t("dashboard.data_quality_score", "Data quality score");
    const scoreVal = document.createElement("div");
    scoreVal.className = "admin-dq-center-value";
    scoreVal.textContent = dq == null ? this.t("dashboard.not_available", "Not available") : dq + "%";
    scoreWrap.append(scoreLabel, scoreVal);
    body.appendChild(scoreWrap);

    if (reasons.length) {
      const details = document.createElement("details");
      details.className = "admin-dq-center-issues";
      const summary = document.createElement("summary");
      summary.textContent = this.t("dashboard.view_issues", "View data issues");
      details.appendChild(summary);
      const ul = document.createElement("ul");
      reasons.forEach((r) => {
        const li = document.createElement("li");
        li.setAttribute("dir", "auto");
        li.textContent = r.label_ar || r.label_en || "";
        ul.appendChild(li);
      });
      details.appendChild(ul);
      body.appendChild(details);
    } else if (dq != null) {
      const ok = document.createElement("p");
      ok.className = "admin-dq-center-ok";
      ok.textContent = this.t("dashboard.data_quality_ok", "No outstanding data-quality issues detected.");
      body.appendChild(ok);
    }

    const cta = document.createElement("a");
    cta.className = "admin-btn admin-btn-secondary";
    cta.href = "/admin/imported-kindergartens";
    cta.textContent = this.t("dashboard.improve_data", "Improve data quality");
    body.appendChild(cta);
  }

  destroy() {
    this.stopAutoRefresh();
    document.getElementById("refresh-dashboard")?.removeEventListener("click", this._listeners.refresh);
    document.getElementById("retry-dashboard")?.removeEventListener("click",   this._listeners.retry);
    document.getElementById("autoRefreshCheck")?.removeEventListener("change", this._listeners.autoRefreshToggle);
    document.removeEventListener("visibilitychange", this._listeners.visibility);
    Object.values(this.charts).forEach((c) => c?.destroy());
    this.charts = {};
  }
}

window.adminDashboard = new AdminDashboard();
window.AdminDashboard = AdminDashboard;
