/**
 * Admin Dashboard JavaScript
 * Handles dashboard data fetching, KPI rendering, and interactive functionality
 */

class AdminDashboard {
  constructor() {
    this.apiEndpoint = "/api/admin/dashboard";
    this.refreshInterval = 300000; // 5 minutes
    this.intervalId = null;
    this.charts = {};
    this.isLoading = false;

    // Initialize dashboard when DOM is ready
    document.addEventListener("DOMContentLoaded", () => {
      this.init();
    });
  }

  init() {
    console.log("Initializing Admin Dashboard...");

    // Initialize components
    this.initEventListeners();
    this.initCharts();

    // Load initial data
    this.loadDashboardData();

    // Start auto-refresh
    this.startAutoRefresh();
  }

  initEventListeners() {
    // Refresh button
    const refreshBtn = document.getElementById("refresh-dashboard");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        this.loadDashboardData();
      });
    }

    // Retry button
    const retryBtn = document.getElementById("retry-dashboard");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        this.loadDashboardData();
      });
    }

    // Handle window visibility change for auto-refresh
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) {
        this.stopAutoRefresh();
      } else {
        this.startAutoRefresh();
      }
    });
  }

  initCharts() {
    // Initialize Chart.js defaults
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
    console.log("Rendering dashboard with data:", data);

    const normalized = this.normalizePayload(data || {});

    // Render KPI cards
    this.renderKPICards(normalized.kpis);

    // Render charts
    this.renderCharts(normalized.charts);

    // Render activity feed
    this.renderActivityFeed(normalized.recent_activity);

    // Render alerts
    this.renderAlerts(normalized.alerts);

    // Show dashboard content
    this.showDashboardContent();
  }

  normalizePayload(data) {
    const summary = data.summary || {};
    const systemOverview = data.system_overview || {};
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];

    // Backward compatibility: keep supporting legacy "kpis" shape.
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
    if (!Array.isArray(alerts) || alerts.length === 0) {
      return [];
    }

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

    const kpiConfig = [
      {
        key: "total_users",
        icon: "fas fa-users",
        color: "primary",
        format: "number",
      },
      {
        key: "active_users",
        icon: "fas fa-user-check",
        color: "success",
        format: "number",
      },
      {
        key: "total_kindergartens",
        icon: "fas fa-school",
        color: "info",
        format: "number",
      },
      {
        key: "active_kindergartens",
        icon: "fas fa-school-circle-check",
        color: "success",
        format: "number",
      },
      {
        key: "total_submissions",
        icon: "fas fa-file-alt",
        color: "warning",
        format: "number",
      },
      {
        key: "pending_submissions",
        icon: "fas fa-clock",
        color: "danger",
        format: "number",
      },
      {
        key: "page_load_time",
        icon: "fas fa-stopwatch",
        color: "secondary",
        format: "duration",
      },
      {
        key: "data_quality_score",
        icon: "fas fa-chart-line",
        color: "primary",
        format: "percentage",
      },
    ];

    kpiConfig.forEach((config) => {
      const value = kpis[config.key];
      if (value !== undefined) {
        const card = this.createKPICard(config, value);
        container.appendChild(card);
      }
    });
  }

  createKPICard(config, value) {
    const card = document.createElement("div");
    card.className = "admin-kpi-card";

    let formattedValue = value;
    let subtitle = "";

    switch (config.format) {
      case "percentage":
        formattedValue = `${value}%`;
        break;
      case "duration":
        formattedValue = `${this.getPageLoadDuration().toFixed(2)}s`;
        subtitle = "Measured from this page load";
        break;
      case "number":
        formattedValue = this.formatNumber(value);
        break;
      default:
        formattedValue = value;
    }

    card.innerHTML = `
            <div class="admin-kpi-card-icon admin-kpi-card-${config.color}">
                <i class="${config.icon}"></i>
            </div>
            <div class="admin-kpi-card-content">
                <div class="admin-kpi-card-value">${formattedValue}</div>
                <div class="admin-kpi-card-title" data-i18n="dashboard.${config.key}">${this.formatTitle(config.key)}</div>
                ${subtitle ? `<div class="admin-kpi-card-subtitle">${subtitle}</div>` : ""}
            </div>
        `;

    return card;
  }

  renderCharts(charts) {
    // User Activity Chart
    if (charts.user_activity) {
      this.renderUserActivityChart(charts.user_activity);
    }

    // Data Submissions Chart
    if (charts.data_submissions) {
      this.renderDataSubmissionsChart(charts.data_submissions);
    }
  }

  renderUserActivityChart(data) {
    const ctx = document.getElementById("user-activity-chart");
    if (!ctx) return;

    // Destroy existing chart
    if (this.charts.userActivity) {
      this.charts.userActivity.destroy();
    }

    this.charts.userActivity = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: this.t("dashboard.active_users", "Active users"),
            data: data.values,
            borderColor: "rgb(54, 162, 235)",
            backgroundColor: "rgba(54, 162, 235, 0.1)",
            tension: 0.4,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
          },
          tooltip: {
            mode: "index",
            intersect: false,
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              precision: 0,
            },
          },
        },
      },
    });
  }

  renderDataSubmissionsChart(data) {
    const ctx = document.getElementById("data-submissions-chart");
    if (!ctx) return;

    // Destroy existing chart
    if (this.charts.dataSubmissions) {
      this.charts.dataSubmissions.destroy();
    }

    this.charts.dataSubmissions = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label: this.t("dashboard.total_submissions", "Total submissions"),
            data: data.values,
            backgroundColor: "rgba(255, 159, 64, 0.8)",
            borderColor: "rgb(255, 159, 64)",
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: "top",
          },
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              precision: 0,
            },
          },
        },
      },
    });
  }

  renderActivityFeed(activities) {
    const container = document.getElementById("activity-feed");
    if (!container) return;

    container.innerHTML = "";

    if (!activities || activities.length === 0) {
      container.innerHTML =
        '<p class="admin-no-data" data-i18n="dashboard.no_recent_activity">No recent activity</p>';
      return;
    }

    activities.forEach((activity) => {
      const item = this.createActivityItem(activity);
      container.appendChild(item);
    });
  }

  createActivityItem(activity) {
    const item = document.createElement("div");
    item.className = "admin-activity-item";

    const timeAgo = this.formatTimeAgo(activity.timestamp);

    item.innerHTML = `
            <div class="admin-activity-icon">
                <i class="${this.getActivityIcon(activity.type)}"></i>
            </div>
            <div class="admin-activity-content">
                <div class="admin-activity-message">${escapeHtml(activity.message)}</div>
                <div class="admin-activity-time">${timeAgo}</div>
            </div>
        `;

    return item;
  }

  renderAlerts(alerts) {
    const container = document.getElementById("alerts-list");
    if (!container) return;

    container.innerHTML = "";

    if (!alerts || alerts.length === 0) {
      container.innerHTML =
        '<p class="admin-no-data" data-i18n="dashboard.no_alerts">No active alerts</p>';
      return;
    }

    alerts.forEach((alert) => {
      const alertItem = this.createAlertItem(alert);
      container.appendChild(alertItem);
    });
  }

  createAlertItem(alert) {
    const item = document.createElement("div");
    item.className = `admin-alert-item admin-alert-${alert.severity}`;

    item.innerHTML = `
            <div class="admin-alert-icon">
                <i class="${this.getAlertIcon(alert.severity)}"></i>
            </div>
            <div class="admin-alert-content">
                <div class="admin-alert-message">${escapeHtml(alert.message)}</div>
                <div class="admin-alert-time">${this.formatTimeAgo(alert.timestamp)}</div>
            </div>
        `;

    return item;
  }

  // Utility methods
  formatNumber(num) {
    return new Intl.NumberFormat().format(num);
  }

  toNumber(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  formatTitle(key) {
    return key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  }

  getPageLoadDuration() {
    if (window.performance?.timing?.navigationStart) {
      const elapsed = Date.now() - window.performance.timing.navigationStart;
      return Math.max(elapsed / 1000, 0);
    }
    return 0;
  }

  formatTimeAgo(timestamp) {
    const now = new Date();
    const time = new Date(timestamp);
    const diff = now - time;

    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);

    if (minutes < 1) return this.t("common.just_now", "just now");
    if (minutes < 60)
      return `${minutes} ${this.t("common.minutes_ago", "minutes ago")}`;
    if (hours < 24)
      return `${hours} ${this.t("common.hours_ago", "hours ago")}`;
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
    const icons = {
      user_login: "fas fa-sign-in-alt",
      user_logout: "fas fa-sign-out-alt",
      data_submit: "fas fa-upload",
      user_create: "fas fa-user-plus",
      system_update: "fas fa-cog",
    };
    return icons[type] || "fas fa-info-circle";
  }

  getAlertIcon(severity) {
    const icons = {
      critical: "fas fa-exclamation-triangle",
      warning: "fas fa-exclamation-circle",
      info: "fas fa-info-circle",
      success: "fas fa-check-circle",
    };
    return icons[severity] || "fas fa-info-circle";
  }

  // UI state management
  showLoading() {
    const loading = document.getElementById("dashboard-loading");
    const content = document.getElementById("dashboard-content");
    const error = document.getElementById("dashboard-error");

    if (loading) loading.style.display = "flex";
    if (content) content.style.display = "none";
    if (error) error.style.display = "none";
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
    const error = document.getElementById("dashboard-error");
    const errorMsg = document.getElementById("error-message");
    const content = document.getElementById("dashboard-content");
    const loading = document.getElementById("dashboard-loading");

    if (error) error.style.display = "flex";
    if (errorMsg) errorMsg.textContent = message;
    if (content) content.style.display = "none";
    if (loading) loading.style.display = "none";
  }

  hideError() {
    const error = document.getElementById("dashboard-error");
    if (error) error.style.display = "none";
  }

  startAutoRefresh() {
    this.stopAutoRefresh(); // Clear any existing interval
    this.intervalId = setInterval(() => {
      this.loadDashboardData();
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
    // Destroy charts
    Object.values(this.charts).forEach((chart) => {
      if (chart) chart.destroy();
    });
    this.charts = {};
  }
}

// Initialize dashboard when script loads
window.adminDashboard = new AdminDashboard();

// Export for global access if needed
window.AdminDashboard = AdminDashboard;
