/**
 * Admin Dashboard JavaScript
 * Handles dashboard data fetching, KPI rendering, and interactive functionality
 * safeChartData() is provided globally by chart_utils.js (loaded before this script).
 */

/** Shared HTML escaping — used to safely insert API strings into innerHTML */
function escapeHtml(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

class AdminDashboard {
  constructor() {
    this.apiEndpoint = "/api/admin/dashboard";
    this.refreshInterval = 300000; // 5 minutes
    this.intervalId = null;
    this.charts = {};
    this.isLoading = false;

    document.addEventListener("DOMContentLoaded", () => {
      this.init();
    });
  }

  init() {
    this.initEventListeners();
    this.initCharts();
    this.loadDashboardData();
    this.startAutoRefresh();
  }

  initEventListeners() {
    const refreshBtn = document.getElementById("refresh-dashboard");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        this.loadDashboardData();
      });
    }

    const retryBtn = document.getElementById("retry-dashboard");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        this.loadDashboardData();
      });
    }

    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.stopAutoRefresh();
      } else {
        this.startAutoRefresh();
      }
    });
  }

  initCharts() {
    if (typeof Chart === "undefined") return;
    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.display = true;
    Chart.defaults.plugins.legend.position = "bottom";
  }

  async loadDashboardData() {
    if (this.isLoading) return;

    this.isLoading = true;
    this.showLoading();

    try {
      const response = await fetch(this.apiEndpoint, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      this.renderDashboard(data);
      this.hideLoading();
      this.hideError();
    } catch (error) {
      console.error("Error loading dashboard data:", error);
      this.showError(error.message);
      this.hideLoading();
    } finally {
      this.isLoading = false;
    }
  }

  renderDashboard(data) {
    const normalized = this.normalizePayload(data || {});
    this.renderKPICards(normalized.kpis);
    this.renderCharts(normalized.charts);
    this.renderActivityFeed(normalized.recent_activity);
    this.renderAlerts(normalized.alerts);
    this.showDashboardContent();
  }

  normalizePayload(data) {
    const summary = data.summary || {};
    const systemOverview = data.system_overview || {};
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];

    const kpis = data.kpis || {
      total_users: this.toNumber(systemOverview.total_users),
      active_users: this.toNumber(summary.attendance_today),
      total_kindergartens: this.toNumber(systemOverview.total_kindergartens),
      active_kindergartens: this.toNumber(systemOverview.active_kindergartens),
      total_submissions: this.toNumber(summary.pending_applications),
      pending_submissions: this.toNumber(summary.pending_daily_reports),
      page_load_time: this.getPageLoadDuration(),
      data_quality_score: this.toNumber(summary.attendance_rate),
    };

    const chartPayload = data.charts || {};
    const userActivityChart = chartPayload.user_activity || {
      labels: Array.isArray(chartPayload.attendance)
        ? chartPayload.attendance.map((item) => item.date)
        : [],
      values: Array.isArray(chartPayload.attendance)
        ? chartPayload.attendance.map((item) => this.toNumber(item.value))
        : [],
    };

    const enrollment = chartPayload.enrollment || {};
    const submissionChart = chartPayload.data_submissions || {
      labels: Object.keys(enrollment),
      values: Object.values(enrollment).map((value) => this.toNumber(value)),
    };

    const recentActivity = Array.isArray(data.recent_activity)
      ? data.recent_activity
      : this.buildRecentActivityFromAlerts(alerts);

    return {
      kpis,
      charts: {
        user_activity: userActivityChart,
        data_submissions: submissionChart,
      },
      recent_activity: recentActivity,
      alerts,
    };
  }

  buildRecentActivityFromAlerts(alerts) {
    if (!Array.isArray(alerts) || alerts.length === 0) return [];
    return alerts.slice(0, 5).map((alert) => ({
      type: "system_update",
      message: alert.title || alert.message || "System update",
      timestamp: alert.timestamp,
    }));
  }

  renderKPICards(kpis) {
    const container = document.getElementById("kpi-cards");
    if (!container) return;

    container.innerHTML = "";

    // All icons use Bootstrap Icons (bi bi-*) — Font Awesome is NOT loaded
    const kpiConfig = [
      { key: "total_users",          icon: "bi bi-people-fill",       color: "primary",   format: "number" },
      { key: "active_users",         icon: "bi bi-person-check-fill", color: "success",   format: "number" },
      { key: "total_kindergartens",  icon: "bi bi-house-fill",        color: "info",      format: "number" },
      { key: "active_kindergartens", icon: "bi bi-house-check-fill",  color: "success",   format: "number" },
      { key: "total_submissions",    icon: "bi bi-file-earmark-fill", color: "warning",   format: "number" },
      { key: "pending_submissions",  icon: "bi bi-clock-fill",        color: "danger",    format: "number" },
      { key: "page_load_time",       icon: "bi bi-stopwatch-fill",    color: "secondary", format: "duration" },
      { key: "data_quality_score",   icon: "bi bi-graph-up-arrow",    color: "primary",   format: "percentage" },
    ];

    // English fallbacks for every KPI key — used only when i18n has not loaded
    this._kpiFallbacks = {
      total_users:          "Total Users",
      active_users:         "Active Users",
      total_kindergartens:  "Total Kindergartens",
      active_kindergartens: "Active Kindergartens",
      total_submissions:    "Total Submissions",
      pending_submissions:  "Pending Submissions",
      page_load_time:       "Page Load Time",
      data_quality_score:   "Data Quality",
    };

    kpiConfig.forEach((config) => {
      const value = kpis[config.key];
      if (value !== undefined) {
        container.appendChild(this.createKPICard(config, value));
      }
    });
  }

  createKPICard(config, value) {
    const card = document.createElement("div");
    card.className = "admin-kpi-card";
    card.setAttribute("role", "region");
    card.setAttribute("aria-label", this.formatTitle(config.key));

    let formattedValue = value;
    let subtitle = "";

    switch (config.format) {
      case "percentage":
        formattedValue = `${value}%`;
        break;
      case "duration":
        // Capture page-load duration once at construction time, not on every auto-refresh
        formattedValue = `${this.getPageLoadDuration().toFixed(2)}s`;
        subtitle = this.t("dashboard.page_load_subtitle", "System performance");
        break;
      case "number":
        formattedValue = this.formatNumber(value);
        break;
      default:
        formattedValue = String(value);
    }

    // Build card using DOM methods to avoid innerHTML XSS risk on value
    const iconDiv = document.createElement("div");
    iconDiv.className = `admin-kpi-card-icon admin-kpi-card-${config.color}`;
    const iconEl = document.createElement("i");
    iconEl.className = config.icon;
    iconEl.setAttribute("aria-hidden", "true");
    iconDiv.appendChild(iconEl);

    const contentDiv = document.createElement("div");
    contentDiv.className = "admin-kpi-card-content";

    const valueDiv = document.createElement("div");
    valueDiv.className = "admin-kpi-card-value";
    valueDiv.textContent = formattedValue;

    const titleDiv = document.createElement("div");
    titleDiv.className = "admin-kpi-card-title";
    titleDiv.setAttribute("data-i18n", `dashboard.${config.key}`);
    const fallback = (this._kpiFallbacks || {})[config.key] || this.formatTitle(config.key);
    titleDiv.textContent = this.t(`dashboard.${config.key}`, fallback);

    contentDiv.appendChild(valueDiv);
    contentDiv.appendChild(titleDiv);

    if (subtitle) {
      const subDiv = document.createElement("div");
      subDiv.className = "admin-kpi-card-subtitle";
      subDiv.textContent = subtitle;
      contentDiv.appendChild(subDiv);
    }

    card.appendChild(iconDiv);
    card.appendChild(contentDiv);
    return card;
  }

  renderCharts(charts) {
    if (typeof Chart === "undefined") return;
    if (charts.user_activity) this.renderUserActivityChart(charts.user_activity);
    if (charts.data_submissions) this.renderDataSubmissionsChart(charts.data_submissions);
  }

  renderUserActivityChart(data) {
    const ctx = document.getElementById("user-activity-chart");
    if (!ctx) return;

    if (this.charts.userActivity) this.charts.userActivity.destroy();

    this.charts.userActivity = new Chart(ctx, {
      type: "line",
      data: {
        labels: safeChartData(data.labels),
        datasets: [{
          label: this.t("dashboard.active_users", "Active users"),
          data: safeChartData(data.values),
          borderColor: "rgb(54, 162, 235)",
          backgroundColor: "rgba(54, 162, 235, 0.1)",
          tension: 0.4,
          fill: true,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: "top" },
          tooltip: { mode: "index", intersect: false },
        },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  renderDataSubmissionsChart(data) {
    const ctx = document.getElementById("data-submissions-chart");
    if (!ctx) return;

    if (this.charts.dataSubmissions) this.charts.dataSubmissions.destroy();

    this.charts.dataSubmissions = new Chart(ctx, {
      type: "bar",
      data: {
        labels: safeChartData(data.labels),
        datasets: [{
          label: this.t("dashboard.total_submissions", "Total submissions"),
          data: safeChartData(data.values),
          backgroundColor: "rgba(255, 159, 64, 0.8)",
          borderColor: "rgb(255, 159, 64)",
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true, position: "top" } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
      },
    });
  }

  renderActivityFeed(activities) {
    const container = document.getElementById("activity-feed");
    if (!container) return;

    container.innerHTML = "";

    if (!activities || activities.length === 0) {
      const wrapper = document.createElement("div");
      wrapper.className = "admin-empty-state";

      const p = document.createElement("p");
      p.className = "admin-no-data";
      p.setAttribute("data-i18n", "dashboard.no_recent_activity");
      p.textContent = this.t("dashboard.no_recent_activity", "No recent activity");

      const hint = document.createElement("p");
      hint.className = "admin-no-data-hint";
      hint.setAttribute("data-i18n", "dashboard.no_activity_hint");
      hint.textContent = this.t("dashboard.no_activity_hint", "Add users or monitor operations to see activity here");

      wrapper.appendChild(p);
      wrapper.appendChild(hint);
      container.appendChild(wrapper);
      return;
    }

    activities.forEach((activity) => {
      container.appendChild(this.createActivityItem(activity));
    });
  }

  createActivityItem(activity) {
    const item = document.createElement("div");
    item.className = "admin-activity-item";

    const iconDiv = document.createElement("div");
    iconDiv.className = "admin-activity-icon";
    const icon = document.createElement("i");
    icon.className = this.getActivityIcon(activity.type);
    icon.setAttribute("aria-hidden", "true");
    iconDiv.appendChild(icon);

    const contentDiv = document.createElement("div");
    contentDiv.className = "admin-activity-content";

    const msgDiv = document.createElement("div");
    msgDiv.className = "admin-activity-message";
    msgDiv.textContent = activity.message || ""; // textContent — never innerHTML

    const timeDiv = document.createElement("div");
    timeDiv.className = "admin-activity-time";
    timeDiv.textContent = this.formatTimeAgo(activity.timestamp);

    contentDiv.appendChild(msgDiv);
    contentDiv.appendChild(timeDiv);
    item.appendChild(iconDiv);
    item.appendChild(contentDiv);
    return item;
  }

  renderAlerts(alerts) {
    const container = document.getElementById("alerts-list");
    if (!container) return;

    container.innerHTML = "";

    if (!alerts || alerts.length === 0) {
      const p = document.createElement("p");
      p.className = "admin-no-data";
      p.setAttribute("data-i18n", "dashboard.no_alerts");
      p.textContent = this.t("dashboard.no_alerts", "No active alerts");
      container.appendChild(p);
      return;
    }


    alerts.forEach((alert) => {
      container.appendChild(this.createAlertItem(alert));
    });
  }

  createAlertItem(alert) {
    const item = document.createElement("div");
    item.className = `admin-alert-item admin-alert-${alert.severity || "info"}`;
    item.setAttribute("role", "listitem");

    const iconDiv = document.createElement("div");
    iconDiv.className = "admin-alert-icon";
    const icon = document.createElement("i");
    icon.className = this.getAlertIcon(alert.severity);
    icon.setAttribute("aria-hidden", "true");
    iconDiv.appendChild(icon);

    const contentDiv = document.createElement("div");
    contentDiv.className = "admin-alert-content";

    const msgDiv = document.createElement("div");
    msgDiv.className = "admin-alert-message";
    msgDiv.textContent = alert.message || ""; // textContent — never innerHTML

    const timeDiv = document.createElement("div");
    timeDiv.className = "admin-alert-time";
    timeDiv.textContent = this.formatTimeAgo(alert.timestamp);

    contentDiv.appendChild(msgDiv);
    contentDiv.appendChild(timeDiv);
    item.appendChild(iconDiv);
    item.appendChild(contentDiv);
    return item;
  }

  // ── Utilities ────────────────────────────────────────────────────────────────

  formatNumber(num) {
    const locale = this.t("common.locale", "en-US");
    return new Intl.NumberFormat(locale).format(num);
  }

  toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  formatTitle(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  }

  getPageLoadDuration() {
    try {
      // Prefer the modern PerformanceNavigationTiming API
      const entries = performance.getEntriesByType("navigation");
      if (entries.length > 0) {
        return Math.max(entries[0].loadEventEnd / 1000, 0);
      }
      // Fallback for older browsers
      if (window.performance?.timing?.navigationStart) {
        return Math.max((Date.now() - window.performance.timing.navigationStart) / 1000, 0);
      }
    } catch (_) {
      // Performance API unavailable
    }
    return 0;
  }

  formatTimeAgo(timestamp) {
    if (!timestamp) return "";
    const now = new Date();
    const time = new Date(timestamp);
    if (isNaN(time.getTime())) return "";

    const diff = now - time;
    const minutes = Math.floor(diff / 60000);
    const hours   = Math.floor(diff / 3600000);
    const days    = Math.floor(diff / 86400000);

    if (minutes < 1)  return this.t("common.just_now",     "just now");
    if (minutes < 60) return `${minutes} ${this.t("common.minutes_ago", "minutes ago")}`;
    if (hours   < 24) return `${hours} ${this.t("common.hours_ago",   "hours ago")}`;
    return `${days} ${this.t("common.days_ago", "days ago")}`;
  }

  t(key, fallback = "") {
    const i18n = window.AdminI18n;
    if (i18n && typeof i18n.translate === "function") {
      return i18n.translate(key, fallback);
    }
    return fallback || key;
  }

  getActivityIcon(type) {
    // Bootstrap Icons only — bi bi-* class names
    const icons = {
      user_login:    "bi bi-box-arrow-in-right",
      user_logout:   "bi bi-box-arrow-left",
      data_submit:   "bi bi-upload",
      user_create:   "bi bi-person-plus-fill",
      system_update: "bi bi-gear-fill",
    };
    return icons[type] || "bi bi-info-circle-fill";
  }

  getAlertIcon(severity) {
    // Bootstrap Icons only
    const icons = {
      critical: "bi bi-exclamation-triangle-fill",
      warning:  "bi bi-exclamation-circle-fill",
      info:     "bi bi-info-circle-fill",
      success:  "bi bi-check-circle-fill",
    };
    return icons[severity] || "bi bi-info-circle-fill";
  }

  // ── UI State ─────────────────────────────────────────────────────────────────

  showLoading() {
    const loading = document.getElementById("dashboard-loading");
    const content = document.getElementById("dashboard-content");
    const error   = document.getElementById("dashboard-error");
    if (loading) loading.style.display = "flex";
    if (content) content.style.display = "none";
    if (error)   error.style.display   = "none";
  }

  hideLoading() {
    const loading = document.getElementById("dashboard-loading");
    if (loading) loading.style.display = "none";
  }

  showDashboardContent() {
    const content = document.getElementById("dashboard-content");
    if (content) content.style.display = "block";
  }

  showError(message) {
    const error   = document.getElementById("dashboard-error");
    const errMsg  = document.getElementById("error-message");
    const content = document.getElementById("dashboard-content");
    const loading = document.getElementById("dashboard-loading");
    if (error)   error.style.display   = "flex";
    if (errMsg)  errMsg.textContent    = message;
    if (content) content.style.display = "none";
    if (loading) loading.style.display = "none";
  }

  hideError() {
    const error = document.getElementById("dashboard-error");
    if (error) error.style.display = "none";
  }

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.intervalId = setInterval(() => {
      this.loadDashboardData(); // isLoading guard inside loadDashboardData prevents overlap
    }, this.refreshInterval);
  }

  stopAutoRefresh() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  destroy() {
    this.stopAutoRefresh();
    Object.values(this.charts).forEach((chart) => { if (chart) chart.destroy(); });
    this.charts = {};
  }
}

window.adminDashboard = new AdminDashboard();
window.AdminDashboard = AdminDashboard;
