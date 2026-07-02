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
    this.startAutoRefresh();
  }

  initEventListeners() {
    this._listeners.refresh    = () => this.loadDashboardData();
    this._listeners.retry      = () => this.loadDashboardData();
    this._listeners.visibility = () => { document.hidden ? this.stopAutoRefresh() : this.startAutoRefresh(); };

    document.getElementById("refresh-dashboard")?.addEventListener("click", this._listeners.refresh);
    document.getElementById("retry-dashboard")?.addEventListener("click",   this._listeners.retry);
    document.addEventListener("visibilitychange", this._listeners.visibility);
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
    } catch (error) {
      clearTimeout(timeoutId);
      console.error("[AdminDashboard] load error:", error);
      const isTimeout = error.name === "AbortError";
      this._setErrorMessage(this.t(
        isTimeout ? "errors.request_timeout" : "errors.generic_error",
        isTimeout ? "Request timed out. Please try again." : "An error occurred. Please try again."
      ));
      this.setState("error");
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
  // text stuck on their (English) fallback. Poll for a canary key, bounded,
  // and re-render exactly once when translations land — never again after
  // that, so later user-driven refreshes don't get needlessly re-rendered.
  _waitForI18nThenRefresh(attemptsLeft = 20) {
    if (this._i18nRefreshed) return;
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    const canary = window.AdminI18n?.translations?.[lang]?.dashboard?.trend_compare_period;
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
    this.renderActivityFeed(normalized.recent_activity);
    this.renderAlerts(normalized.alerts);
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
    const card = document.createElement("div");
    card.className = "admin-kpi-card";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", this.t(`dashboard.${config.key}`, KPI_LABEL_FALLBACK[config.key]));

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

    const titleDiv = document.createElement("div");
    titleDiv.className = "admin-kpi-card-title";
    titleDiv.setAttribute("data-i18n", `dashboard.${config.key}`);
    titleDiv.textContent = this.t(`dashboard.${config.key}`, KPI_LABEL_FALLBACK[config.key] || config.key);
    contentDiv.appendChild(titleDiv);

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
    const lang    = window.KINJO_LANG === "en" ? "en" : "ar";
    const message = activity[`message_${lang}`] || activity.message || "";

    const article = document.createElement("article");
    article.className = "admin-activity-item";
    article.setAttribute("role", "listitem");

    const header = document.createElement("header");
    header.className = "admin-activity-item-header";

    const iconWrap = document.createElement("span");
    iconWrap.className = "admin-activity-icon";
    const icon = document.createElement("i");
    icon.className = this.getActivityIcon(activity.type);
    icon.setAttribute("aria-hidden", "true");
    iconWrap.appendChild(icon);
    header.appendChild(iconWrap);

    const userName = document.createElement("strong");
    userName.className = "admin-activity-user";
    userName.setAttribute("dir", "auto");
    userName.textContent = activity.user_name || this.t("dashboard.system_actor", "System");
    header.appendChild(userName);

    const time = document.createElement("span");
    time.className = "admin-activity-time";
    time.textContent = this.formatTimeAgo(activity.timestamp);
    header.appendChild(time);

    article.appendChild(header);

    const messageEl = document.createElement("p");
    messageEl.className = "admin-activity-message";
    messageEl.setAttribute("dir", "auto");
    messageEl.textContent = message;
    article.appendChild(messageEl);

    const dl = document.createElement("dl");
    dl.className = "admin-activity-meta";

    const addTerm = (termKey, termFallback, value, ddClass) => {
      if (!value) return;
      const dt = document.createElement("dt");
      dt.textContent = this.t(termKey, termFallback);
      const dd = document.createElement("dd");
      if (ddClass) dd.className = ddClass;
      dd.textContent = value;
      dl.appendChild(dt);
      dl.appendChild(dd);
    };

    addTerm("dashboard.activity_role",     "Role",     this.formatRole(activity.user_role));
    addTerm("dashboard.activity_module",   "Module",   lang === "en" ? activity.module_en : activity.module_ar);
    addTerm("dashboard.activity_entity",   "Entity",   lang === "en" ? activity.entity_label_en : activity.entity_label_ar);
    addTerm("dashboard.activity_status",   "Status",   this.formatStatus(activity.status), `admin-activity-status admin-activity-status--${activity.status || "success"}`);
    addTerm("dashboard.activity_severity", "Severity", this.formatSeverity(activity.severity), `admin-activity-severity admin-activity-severity--${activity.severity || "low"}`);

    if (dl.children.length > 0) article.appendChild(dl);

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
    return {
      critical: "bi bi-exclamation-triangle-fill",
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

  destroy() {
    this.stopAutoRefresh();
    document.getElementById("refresh-dashboard")?.removeEventListener("click", this._listeners.refresh);
    document.getElementById("retry-dashboard")?.removeEventListener("click",   this._listeners.retry);
    document.removeEventListener("visibilitychange", this._listeners.visibility);
    Object.values(this.charts).forEach((c) => c?.destroy());
    this.charts = {};
  }
}

window.adminDashboard = new AdminDashboard();
window.AdminDashboard = AdminDashboard;
