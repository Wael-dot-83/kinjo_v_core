/**
 * Admin Dashboard — KinJo v2.8
 * Handles KPI rendering, charts, activity feed, alerts, mission KPIs,
 * action center, security center, government readiness, and data quality.
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
    this.renderHeroStatus(normalized.hero_status);
    this.renderMissionKPIs(normalized.mission_kpis, normalized.kpi_trends, normalized.data_quality_reasons);
    this.renderActionCenter(normalized.action_center);
    this.renderCharts(normalized.charts);
    if (!document.getElementById("activity-filter-bar")) {
      this.renderActivityFeed(normalized.recent_activity);
    }
    this.renderActivitySummary(normalized.activity_summary);
    this.renderAlerts(normalized.alerts);
    this.renderSecurityCenter(normalized.security_summary);
    this.renderGovernmentReadiness(normalized.government_readiness);
    this.renderDataQualityProgress(normalized.data_quality_reasons);
    // Translate any data-i18n elements injected dynamically by this script
    window.AdminI18n?.translatePage?.();
  }

  /**
   * Map API response shape to internal normalized form.
   * The API returns { kpis, summary, system_overview, charts, alerts, recent_activity, ... }.
   */
  normalizePayload(data) {
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    const lang   = window.KINJO_LANG === "en" ? "en" : "ar";

    const kpis = data.kpis || {};
    const kpiTrends = data.kpi_trends || {};
    const dataQualityReasons = Array.isArray(data.data_quality_reasons) ? data.data_quality_reasons : [];
    const heroStatus = data.hero_status || null;
    const missionKpis = Array.isArray(data.mission_kpis) ? data.mission_kpis : [];
    const actionCenter = Array.isArray(data.action_center) ? data.action_center : [];
    const securitySummary = data.security_summary || null;
    const governmentReadiness = Array.isArray(data.government_readiness) ? data.government_readiness : [];
    const activitySummary = data.activity_summary || null;

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
      hero_status: heroStatus,
      mission_kpis: missionKpis,
      action_center: actionCenter,
      security_summary: securitySummary,
      government_readiness: governmentReadiness,
      activity_summary: activitySummary,
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

  // ── Hero Status ─────────────────────────────────────────────────────────────

  renderHeroStatus(heroStatus) {
    const container = document.getElementById("hero-status");
    if (!container) return;
    const card = container.querySelector(".admin-hero-card");
    if (!card) return;
    if (!heroStatus) {
      card.style.display = "none";
      return;
    }
    card.style.display = "";
    card.dataset.state = heroStatus.status || "healthy";
    const titleEl = card.querySelector(".admin-hero-subtitle");
    if (titleEl) {
      const lang = window.KINJO_LANG === "en" ? "en" : "ar";
      titleEl.textContent = lang === "en" ? (heroStatus.status_title_en || "Operational") : (heroStatus.status_title_ar || "يعمل بشكل طNormal");
    }
    const reviewLi = document.getElementById("hero-review-count");
    if (reviewLi && heroStatus.requests_needing_review !== undefined) {
      const span = reviewLi.querySelector("span");
      if (span) {
        const lang = window.KINJO_LANG === "en" ? "en" : "ar";
        span.textContent = this.t(
          "hero.requests_needing_review",
          lang === "en" ? `${heroStatus.requests_needing_review} requests need review` : `${heroStatus.requests_needing_review} طلب بحاجة للمراجعة`,
          { count: String(heroStatus.requests_needing_review) }
        );
      }
    }
  }

  // ── Mission KPIs ────────────────────────────────────────────────────────────

  renderMissionKPIs(missionKpis, kpiTrends, dataQualityReasons) {
    const container = document.getElementById("mission-kpi-cards");
    if (!container) return;
    container.innerHTML = "";
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    (Array.isArray(missionKpis) ? missionKpis : []).forEach((kpi) => {
      const card = document.createElement("li");
      card.className = "admin-kpi-card admin-kpi-card--mission";

      const iconWrap = document.createElement("div");
      iconWrap.className = `admin-kpi-card-icon admin-kpi-card-icon--${kpi.color || "primary"}`;
      const icon = document.createElement("i");
      icon.className = kpi.icon || "bi bi-circle";
      icon.setAttribute("aria-hidden", "true");
      iconWrap.appendChild(icon);

      const content = document.createElement("div");
      content.className = "admin-kpi-card-content";

      const value = document.createElement("div");
      value.className = "admin-kpi-card-value";
      const num = Number(kpi.value);
      value.textContent = Number.isFinite(num) ? new Intl.NumberFormat(lang === "en" ? "en-US" : "ar-JO").format(num) : "—";
      content.appendChild(value);

      const title = document.createElement("h3");
      title.className = "admin-kpi-card-title";
      title.textContent = lang === "en" ? (kpi.label_en || kpi.key) : (kpi.label_ar || kpi.key);
      content.appendChild(title);

      if (kpi.helper_ar || kpi.helper_en) {
        const helper = document.createElement("p");
        helper.className = "admin-kpi-card-helper";
        helper.textContent = lang === "en" ? (kpi.helper_en || "") : (kpi.helper_ar || "");
        content.appendChild(helper);
      }

      if (kpi.drilldown) {
        const link = document.createElement("a");
        link.className = "admin-kpi-card-drilldown";
        link.href = kpi.drilldown;
        const label = document.createElement("span");
        label.textContent = this.t("dashboard.view_details", lang === "en" ? "View details" : "عرض التفاصيل");
        const chevron = document.createElement("i");
        chevron.className = "bi bi-chevron-left icon-directional";
        chevron.setAttribute("aria-hidden", "true");
        link.appendChild(label);
        link.appendChild(chevron);
        content.appendChild(link);
      }

      card.appendChild(iconWrap);
      card.appendChild(content);
      container.appendChild(card);
    });
  }

  // ── Action Center ───────────────────────────────────────────────────────────

  renderActionCenter(actionCenter) {
    const container = document.getElementById("action-center");
    if (!container) return;
    container.innerHTML = "";
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    const items = Array.isArray(actionCenter) ? actionCenter : [];
    if (items.length === 0) {
      container.appendChild(this.createEmptyState(
        "action_center.no_actions", "No actions required",
        "action_center.no_actions_hint", "All caught up — nice work",
        "bi-check2-circle"
      ));
      return;
    }
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = `admin-action-card admin-action-card--${item.severity || "info"}`;

      const header = document.createElement("div");
      header.className = "admin-action-card-header";

      const icon = document.createElement("i");
      icon.className = item.severity === "error" ? "bi bi-exclamation-triangle-fill" :
                       item.severity === "warning" ? "bi bi-exclamation-circle-fill" :
                       "bi bi-info-circle-fill";
      icon.setAttribute("aria-hidden", "true");
      header.appendChild(icon);

      const title = document.createElement("strong");
      title.textContent = lang === "en" ? (item.label_en || item.label_ar || "") : (item.label_ar || item.label_en || "");
      header.appendChild(title);

      card.appendChild(header);

      const count = document.createElement("div");
      count.className = "admin-action-card-count";
      count.textContent = String(item.count ?? 0);
      card.appendChild(count);

      const explanation = document.createElement("p");
      explanation.className = "admin-action-card-explanation";
      explanation.textContent = lang === "en" ? (item.explanation_en || item.explanation_ar || "") : (item.explanation_ar || item.explanation_en || "");
      card.appendChild(explanation);

      const actions = document.createElement("div");
      actions.className = "admin-action-card-actions";
      if (item.action_url) {
        const link = document.createElement("a");
        link.className = "admin-btn admin-btn-sm admin-btn-primary";
        link.href = item.action_url;
        link.textContent = lang === "en" ? (item.action_label_en || item.action_label_ar || "View") : (item.action_label_ar || item.action_label_en || "عرض");
        actions.appendChild(link);
      }
      if (item.empty_state_ar || item.empty_state_en) {
        const span = document.createElement("span");
        span.className = "admin-action-card-empty";
        span.textContent = (item.count === 0) ? (lang === "en" ? (item.empty_state_en || "") : (item.empty_state_ar || "")) : "";
        actions.appendChild(span);
      }
      card.appendChild(actions);
      container.appendChild(card);
    });
  }

  // ── Security Center ─────────────────────────────────────────────────────────

  renderSecurityCenter(securitySummary) {
    const container = document.getElementById("security-summary");
    if (!container) return;
    container.innerHTML = "";
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    if (!securitySummary) {
      container.appendChild(this.createEmptyState(
        "security.no_data", "No security data available",
        "security.no_data_hint", "Security metrics will appear here",
        "bi-shield-slash"
      ));
      return;
    }
    const isHealthy = securitySummary.status === "healthy";
    const statusClass = isHealthy ? "security-status--healthy" : (securitySummary.status === "degraded" ? "security-status--degraded" : "security-status--critical");
    const statusText = isHealthy
      ? (lang === "en" ? "No critical incidents" : "لا توجد حوادث حرجة")
      : (lang === "en" ? "Needs attention" : "يحتاج متابعة");

    const items = [
      { icon: "bi bi-shield-check", label_ar: "حالة الأمان", label_en: "Security status", value: statusText, cls: statusClass },
      { icon: "bi bi-person-x", label_ar: "محاولات دخول فاشلة", label_en: "Failed logins (24h)", value: String(securitySummary.failed_logins_24h ?? 0) },
      { icon: "bi bi-exclamation-triangle", label_ar: "حوادث حرجة", label_en: "Critical incidents", value: String(securitySummary.critical_incidents_count ?? 0) },
      { icon: "bi bi-calendar-check", label_ar: "آخر فحص", label_en: "Last audit", value: securitySummary.last_audit_date || "—" },
    ];

    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "admin-security-row";

      const iconWrap = document.createElement("div");
      iconWrap.className = "admin-security-icon";
      const iconEl = document.createElement("i");
      iconEl.className = item.icon;
      iconEl.setAttribute("aria-hidden", "true");
      iconWrap.appendChild(iconEl);

      const label = document.createElement("span");
      label.className = "admin-security-label";
      label.textContent = lang === "en" ? item.label_en : item.label_ar;

      const value = document.createElement("span");
      value.className = `admin-security-value${item.cls ? ` ${item.cls}` : ""}`;
      value.textContent = item.value;

      row.appendChild(iconWrap);
      row.appendChild(label);
      row.appendChild(value);
      container.appendChild(row);
    });
  }

  // ── Government Readiness ────────────────────────────────────────────────────

  renderGovernmentReadiness(governmentReadiness) {
    const container = document.getElementById("government-readiness");
    if (!container) return;
    container.innerHTML = "";
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    const items = Array.isArray(governmentReadiness) ? governmentReadiness : [];
    if (items.length === 0) {
      container.appendChild(this.createEmptyState(
        "gov.no_data", "No government report data",
        "gov.no_data_hint", "Report readiness will appear here",
        "bi-building"
      ));
      return;
    }
    items.forEach((item) => {
      const row = document.createElement("div");
      row.className = "admin-gov-row";

      const agency = document.createElement("div");
      agency.className = "admin-gov-agency";
      agency.textContent = lang === "en" ? (item.agency_en || item.agency_ar || "") : (item.agency_ar || item.agency_en || "");

      const status = document.createElement("div");
      status.className = `admin-gov-status admin-gov-status--${item.status || "info"}`;
      status.textContent = lang === "en" ? (item.status_label_en || item.status_label_ar || "") : (item.status_label_ar || item.status_label_en || "");

      const actions = document.createElement("div");
      actions.className = "admin-gov-actions";
      (Array.isArray(item.actions) ? item.actions : []).forEach((act) => {
        const link = document.createElement("a");
        link.className = "admin-btn admin-btn-sm admin-btn-outline-secondary";
        link.href = act.url || "#";
        if (!act.enabled) {
          link.classList.add("disabled");
          link.setAttribute("aria-disabled", "true");
          link.setAttribute("tabindex", "-1");
        }
        link.textContent = lang === "en" ? (act.label_en || act.label_ar || "") : (act.label_ar || act.label_en || "");
        actions.appendChild(link);
      });

      row.appendChild(agency);
      row.appendChild(status);
      row.appendChild(actions);
      container.appendChild(row);
    });
  }

  // ── Data Quality Progress ───────────────────────────────────────────────────

  renderDataQualityProgress(dataQualityReasons) {
    const container = document.getElementById("data-quality-progress");
    if (!container) return;
    container.innerHTML = "";
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    const score = this._dqScoreFromReasons(dataQualityReasons);
    const clamped = Math.max(0, Math.min(100, score));
    const bar = document.createElement("div");
    bar.className = "admin-dq-bar-track";
    const fill = document.createElement("div");
    fill.className = "admin-dq-bar-fill";
    fill.style.width = `${clamped}%`;
    fill.textContent = `${clamped}%`;
    bar.appendChild(fill);

    const scoreText = document.createElement("p");
    scoreText.className = "admin-dq-score";
    scoreText.textContent = this.t("data_quality.score", `${clamped}%`, { pct: String(clamped) });
    bar.appendChild(scoreText);

    const reasonsWrap = document.createElement("div");
    reasonsWrap.className = "admin-dq-reasons";
    const reasons = Array.isArray(dataQualityReasons) ? dataQualityReasons : [];
    if (reasons.length === 0) {
      const empty = document.createElement("p");
      empty.className = "admin-dq-reasons-empty";
      empty.textContent = this.t("data_quality.all_complete", lang === "en" ? "All records complete" : "جميع السجلات مكتملة");
      reasonsWrap.appendChild(empty);
    } else {
      const ul = document.createElement("ul");
      reasons.forEach((r) => {
        const li = document.createElement("li");
        li.setAttribute("dir", "auto");
        li.textContent = lang === "en" ? (r.label_en || r.label_ar || "") : (r.label_ar || r.label_en || "");
        ul.appendChild(li);
      });
      reasonsWrap.appendChild(ul);
    }

    container.appendChild(bar);
    container.appendChild(reasonsWrap);
  }

  _dqScoreFromReasons(dataQualityReasons) {
    const reasons = Array.isArray(dataQualityReasons) ? dataQualityReasons : [];
    if (reasons.length === 0) return 100;
    const issueCount = reasons.reduce((acc, r) => acc + (Number(r.count) || 0), 0);
    const score = 100 - Math.min(100, issueCount * 5);
    return Math.max(0, score);
  }

  // ── Activity Summary ────────────────────────────────────────────────────────

  renderActivitySummary(activitySummary) {
    if (!activitySummary) return;
    const setText = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = new Intl.NumberFormat("ar-JO").format(val);
    };
    setText("act-sum-logins", activitySummary.logins_today || 0);
    setText("act-sum-failed", activitySummary.failed_logins_today || 0);
    setText("act-sum-changes", activitySummary.user_changes_today || 0);
    setText("act-sum-exports", activitySummary.exports_today || 0);
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
