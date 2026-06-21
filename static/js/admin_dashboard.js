/**
 * Admin Dashboard — KinJo v2.7
 * Handles KPI rendering, charts, activity feed, and alerts.
 * Depends on: chart_utils.js (safeChartData), admin_i18n.js (window.AdminI18n)
 * window.KINJO_LANG must be set before this script executes (injected by template).
 */

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
  ACTIVE:     "dashboard.enrollment_active",
  PENDING:    "dashboard.enrollment_pending",
  REJECTED:   "dashboard.enrollment_rejected",
  WITHDRAWN:  "dashboard.enrollment_withdrawn",
  WAITLISTED: "dashboard.enrollment_waitlisted",
};

// Inline fallbacks — used only when JSON hasn't loaded yet
const ENROLLMENT_FALLBACK = {
  ar: { ACTIVE: "نشط", PENDING: "قيد الانتظار", REJECTED: "مرفوض", WITHDRAWN: "منسحب", WAITLISTED: "قائمة الانتظار" },
  en: { ACTIVE: "Active", PENDING: "Pending", REJECTED: "Rejected", WITHDRAWN: "Withdrawn", WAITLISTED: "Waitlisted" },
};

// KPI configuration — single source of truth, order determines render order
const KPI_CONFIG = [
  { key: "total_users",          icon: "bi bi-people-fill",       color: "primary", format: "number" },
  { key: "active_users",         icon: "bi bi-person-check-fill", color: "success", format: "number" },
  { key: "total_kindergartens",  icon: "bi bi-house-fill",        color: "info",    format: "number" },
  { key: "active_kindergartens", icon: "bi bi-house-check-fill",  color: "success", format: "number" },
  { key: "total_submissions",    icon: "bi bi-file-earmark-fill", color: "warning", format: "number" },
  { key: "pending_submissions",  icon: "bi bi-clock-fill",        color: "danger",  format: "number" },
  { key: "data_quality_score",   icon: "bi bi-graph-up-arrow",    color: "primary", format: "percentage" },
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
      this.renderDashboard(data);
      this.setState("success");
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

  // ── Rendering ─────────────────────────────────────────────────────────────

  renderDashboard(data) {
    const normalized = this.normalizePayload(data || {});
    this.renderKPICards(normalized.kpis);
    this.renderCharts(normalized.charts);
    this.renderActivityFeed(normalized.recent_activity);
    this.renderAlerts(normalized.alerts);
    // Translate any data-i18n elements injected dynamically by this script
    window.AdminI18n?.translatePage?.();
  }

  /**
   * Map API response shape to internal normalized form.
   * The API returns { summary, system_overview, charts, alerts, recent_activity }.
   */
  normalizePayload(data) {
    const summary        = data.summary        || {};
    const systemOverview = data.system_overview || {};
    const alerts         = Array.isArray(data.alerts) ? data.alerts : [];

    const kpis = data.kpis || {
      total_users:          this.toNumber(systemOverview.total_users),
      active_users:         this.toNumber(summary.attendance_today),
      total_kindergartens:  this.toNumber(systemOverview.total_kindergartens),
      active_kindergartens: this.toNumber(systemOverview.active_kindergartens),
      total_submissions:    this.toNumber(summary.pending_applications),
      pending_submissions:  this.toNumber(summary.pending_daily_reports),
      data_quality_score:   this.toNumber(summary.attendance_rate),
    };

    const chartPayload = data.charts || {};
    const lang         = window.KINJO_LANG === "en" ? "en" : "ar";

    const userActivityChart = chartPayload.user_activity || {
      labels: Array.isArray(chartPayload.attendance) ? chartPayload.attendance.map((i) => i.date)  : [],
      values: Array.isArray(chartPayload.attendance) ? chartPayload.attendance.map((i) => this.toNumber(i.value)) : [],
    };

    const enrollment      = chartPayload.enrollment || {};
    const submissionChart = chartPayload.data_submissions || {
      labels: Object.keys(enrollment).map((k) => {
        const i18nKey  = ENROLLMENT_I18N[k];
        const fallback = (ENROLLMENT_FALLBACK[lang] || ENROLLMENT_FALLBACK.en)[k] || k;
        return i18nKey ? this.t(i18nKey, fallback) : fallback;
      }),
      values: Object.values(enrollment).map((v) => this.toNumber(v)),
    };

    const recentActivity = Array.isArray(data.recent_activity)
      ? data.recent_activity
      : this.buildRecentActivityFromAlerts(alerts);

    return {
      kpis,
      charts: { user_activity: userActivityChart, data_submissions: submissionChart },
      recent_activity: recentActivity,
      alerts,
    };
  }

  buildRecentActivityFromAlerts(alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) return [];
    return alerts.slice(0, 5).map((a) => ({
      type:      "system_update",
      message:   a.title || a.message || "",
      timestamp: a.timestamp,
    }));
  }

  // ── KPI Cards ─────────────────────────────────────────────────────────────

  renderKPICards(kpis) {
    const container = document.getElementById("kpi-cards");
    if (!container) return;
    container.innerHTML = "";
    // Always render all KPI slots — sanitizeKPIValue returns null for invalid/missing values,
    // which formatKPIValue renders as "—" to preserve layout integrity.
    KPI_CONFIG.forEach((config) => {
      container.appendChild(this.createKPICard(config, this.sanitizeKPIValue(config.key, kpis[config.key])));
    });
  }

  // Returns null for invalid or negative values (renders as "—"), clamped value otherwise.
  sanitizeKPIValue(key, raw) {
    const num = Number(raw);
    if (!Number.isFinite(num) || num < 0) return null;
    if (key === "data_quality_score") return Math.min(100, Math.max(0, num));
    return num;
  }

  createKPICard(config, value) {
    const card = document.createElement("div");
    card.className = "admin-kpi-card";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", this.t(`dashboard.${config.key}`, KPI_LABEL_FALLBACK[config.key] || config.key));

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

    card.appendChild(iconDiv);
    card.appendChild(contentDiv);
    return card;
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
    this.charts.userActivity = new Chart(ctx, {
      type: "line",
      data: {
        labels:   safeChartData(data.labels),
        datasets: [{
          label:           this.t("dashboard.active_users", "Active Users"),
          data:            safeChartData(data.values),
          borderColor:     "#1F5E47",
          backgroundColor: "rgba(31, 94, 71, 0.1)",
          tension:         0.4,
          fill:            true,
        }],
      },
      options: {
        plugins: {
          legend:  { position: "top" },
          tooltip: { mode: "index", intersect: false },
        },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  renderSubmissionsChart(data) {
    const ctx = document.getElementById("data-submissions-chart");
    if (!ctx) return;
    this.charts.dataSubmissions?.destroy();
    this.charts.dataSubmissions = new Chart(ctx, {
      type: "bar",
      data: {
        labels:   safeChartData(data.labels),
        datasets: [{
          label:           this.t("dashboard.enrollment_status", "Enrollment Status"),
          data:            safeChartData(data.values),
          backgroundColor: "rgba(245, 158, 11, 0.8)",
          borderColor:     "#f59e0b",
          borderWidth:     1,
        }],
      },
      options: {
        plugins: { legend: { position: "top" } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
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
        "dashboard.manage_users", "Manage Users", "/admin/users/create"
      ));
      return;
    }
    activities.forEach((a) => container.appendChild(this.createActivityItem(a)));
  }

  createActivityItem(activity) {
    return this._createFeedItem({
      wrapperClass:  "admin-activity-item",
      iconWrapClass: "admin-activity-icon",
      iconClass:     this.getActivityIcon(activity.type),
      contentClass:  "admin-activity-content",
      msgClass:      "admin-activity-message",
      timeClass:     "admin-activity-time",
      message:       activity.message,
      timestamp:     activity.timestamp,
    });
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
    return this._createFeedItem({
      wrapperClass:  `admin-alert-item admin-alert-${alert.severity || "info"}`,
      iconWrapClass: "admin-alert-icon",
      iconClass:     this.getAlertIcon(alert.severity),
      contentClass:  "admin-alert-content",
      msgClass:      "admin-alert-message",
      timeClass:     "admin-alert-time",
      message:       alert.message,
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
