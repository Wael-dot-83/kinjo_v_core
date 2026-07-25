/**
 * Admin Dashboard — KinJo v2.7
 * Handles KPI rendering, charts, activity feed, and alerts.
 * Depends on: chart_utils.js (safeChartData), admin_i18n.js (window.AdminI18n)
 * window.KINJO_LANG must be set before this script executes (injected by template).
 */

window.KINJO_LANG =
  window.KINJO_LANG || (document.documentElement.lang === "en" ? "en" : "ar");

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
  ACTIVE: "dashboard.enrollment_active",
  PENDING: "dashboard.enrollment_pending",
  PENDING_REVIEW: "dashboard.enrollment_pending_review",
  SUBMITTED: "dashboard.enrollment_submitted",
  ACCEPTED: "dashboard.enrollment_accepted",
  REJECTED: "dashboard.enrollment_rejected",
  WITHDRAWN: "dashboard.enrollment_withdrawn",
  WAITLISTED: "dashboard.enrollment_waitlisted",
  DRAFT: "dashboard.enrollment_draft",
};

// Inline fallbacks — used only when JSON hasn't loaded yet
const ENROLLMENT_FALLBACK = {
  ar: {
    ACTIVE: "نشط",
    PENDING: "قيد الانتظار",
    PENDING_REVIEW: "قيد المراجعة",
    SUBMITTED: "مُقدَّم",
    ACCEPTED: "مقبول",
    REJECTED: "مرفوض",
    WITHDRAWN: "منسحب",
    WAITLISTED: "قائمة الانتظار",
    DRAFT: "مسودة",
  },
  en: {
    ACTIVE: "Active",
    PENDING: "Pending",
    PENDING_REVIEW: "Under Review",
    SUBMITTED: "Submitted",
    ACCEPTED: "Accepted",
    REJECTED: "Rejected",
    WITHDRAWN: "Withdrawn",
    WAITLISTED: "Waitlisted",
    DRAFT: "Draft",
  },
};

const ATTENDANCE_CHART_LABELS = {
  "Recorded Attendance": "سجلات الحضور",
};

// KPI configuration — single source of truth, order determines render order
const KPI_CONFIG = [
  {
    key: "total_users",
    icon: "bi bi-people-fill",
    color: "primary",
    format: "number",
    drilldown: "/admin/users",
    drilldownLabelKey: "dashboard.view_users",
  },
  {
    key: "active_users",
    icon: "bi bi-person-check-fill",
    color: "success",
    format: "number",
    drilldown: "/admin/users",
    drilldownLabelKey: "dashboard.view_users",
  },
  {
    key: "total_kindergartens",
    icon: "bi bi-house-fill",
    color: "info",
    format: "number",
    drilldown: "/admin/kg-overview",
    drilldownLabelKey: "dashboard.view_kindergartens",
  },
  {
    key: "active_kindergartens",
    icon: "bi bi-house-check-fill",
    color: "success",
    format: "number",
    drilldown: "/admin/kg-overview",
    drilldownLabelKey: "dashboard.view_kindergartens",
  },
  {
    key: "total_submissions",
    icon: "bi bi-file-earmark-fill",
    color: "warning",
    format: "number",
    drilldown: "/reports/analytics",
    drilldownLabelKey: "dashboard.view_reports",
  },
  {
    key: "pending_submissions",
    icon: "bi bi-clock-fill",
    color: "danger",
    format: "number",
    drilldown: "/reports/analytics",
    drilldownLabelKey: "dashboard.view_reports",
  },
  {
    key: "data_quality_score",
    icon: "bi bi-graph-up-arrow",
    color: "primary",
    format: "percentage",
    drilldown: "/admin/daily-reports-organization",
    drilldownLabelKey: "dashboard.view_data_management",
  },
];

// English fallbacks for KPI labels (used if i18n JSON hasn't loaded yet)
const KPI_LABEL_FALLBACK = {
  total_users: "Total Users",
  active_users: "Users Logged In Today",
  total_kindergartens: "Total Kindergartens",
  active_kindergartens: "Active Kindergartens",
  total_submissions: "Total Submissions",
  pending_submissions: "Pending Submissions",
  data_quality_score: "Data Quality",
};

class AdminDashboard {
  constructor() {
    this.apiEndpoint = "/api/admin/dashboard";
    this.refreshInterval = 300000; // 5 minutes
    this.intervalId = null;
    this.charts = {};
    this.chartRuntimeBroken = false;
    this.chartRuntimeProbeEnabled = this.readRuntimeFlag(
      "chartRuntimeProbeEnabled",
      true,
    );
    this.telemetryEnabled = this.readRuntimeFlag(
      "dashboardTelemetryEnabled",
      true,
    );
    this._chartRuntimeFailureReported = false;
    this.isLoading = false;
    this._listeners = {};

    document.addEventListener("DOMContentLoaded", () => this.init());
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  init() {
    this.initEventListeners();
    this.initChartDefaults();
    this.loadDashboardData();

    // Accessibility: announce timestamp changes to screen readers.
    const lastUpdatedTime = this.getLastUpdatedElement();
    if (lastUpdatedTime) lastUpdatedTime.setAttribute("aria-live", "polite");

    // On-page component reference (explains each section of the dashboard).
    this.renderComponentGuide();

    // Live "updated Xs ago" relative timestamp.
    this.startRelativeTimeTicker();

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
    this._listeners.refresh = () => this.loadDashboardData();
    this._listeners.retry = () => this.loadDashboardData();
    this._listeners.visibility = () => {
      if (document.hidden) {
        this.stopAutoRefresh();
        return;
      }
      if (this.isAutoRefreshEnabled()) this.startAutoRefresh();
    };
    this._listeners.autoRefreshToggle = (event) => {
      localStorage.setItem(
        "autoRefreshEnabled",
        event.target.checked ? "true" : "false",
      );
      if (event.target.checked) this.startAutoRefresh();
      else this.stopAutoRefresh();
    };

    document
      .getElementById("refresh-dashboard")
      ?.addEventListener("click", this._listeners.refresh);
    document
      .getElementById("retry-dashboard")
      ?.addEventListener("click", this._listeners.retry);
    document.addEventListener("visibilitychange", this._listeners.visibility);

    const autoRefreshCheck = document.getElementById("autoRefreshCheck");
    if (autoRefreshCheck) {
      autoRefreshCheck.checked = this.isAutoRefreshEnabled();
      autoRefreshCheck.addEventListener(
        "change",
        this._listeners.autoRefreshToggle,
      );
    }
  }

  initChartDefaults() {
    if (typeof Chart === "undefined") return;

    this.hardenChartScriptableGuards();

    Chart.defaults.responsive = true;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.display = true;
    Chart.defaults.plugins.legend.position = "bottom";

    // Probe Chart.js once at startup (default on). This can be disabled via
    // window.KINJO_ADMIN_FLAGS.chartRuntimeProbeEnabled or localStorage key
    // kinjo.admin.chartRuntimeProbeEnabled for vendor isolation diagnostics.
    if (this.chartRuntimeProbeEnabled) {
      this.chartRuntimeBroken = !this._probeChartRuntime("init");
    }
  }

  readRuntimeFlag(name, defaultValue) {
    const fromWindow =
      typeof window !== "undefined" &&
      window.KINJO_ADMIN_FLAGS &&
      Object.prototype.hasOwnProperty.call(window.KINJO_ADMIN_FLAGS, name)
        ? window.KINJO_ADMIN_FLAGS[name]
        : undefined;

    if (typeof fromWindow === "boolean") return fromWindow;

    try {
      const fromStorage = localStorage.getItem(`kinjo.admin.${name}`);
      if (fromStorage === "true") return true;
      if (fromStorage === "false") return false;
    } catch (_err) {
      // Ignore storage access restrictions and use defaults.
    }

    return defaultValue;
  }

  emitTelemetry(eventName, payload = {}) {
    const details = {
      event: eventName,
      at: new Date().toISOString(),
      page: window.location.pathname,
      lang: window.KINJO_LANG === "en" ? "en" : "ar",
      dir: document?.documentElement?.dir || "rtl",
      ...payload,
    };

    try {
      window.dispatchEvent(
        new CustomEvent("kinjo:dashboard:telemetry", {
          detail: details,
        }),
      );
    } catch (_err) {
      // Ignore environments where CustomEvent is unavailable.
    }

    if (this.telemetryEnabled) {
      console.info("[AdminDashboard][telemetry]", details);
    }
  }

  reportChartRuntimeFailure(reason, payload = {}) {
    if (this._chartRuntimeFailureReported) return;
    this._chartRuntimeFailureReported = true;
    this.emitTelemetry("chart_runtime_failure", {
      reason,
      probeEnabled: this.chartRuntimeProbeEnabled,
      chartRuntimeBroken: this.chartRuntimeBroken,
      userAgent: navigator?.userAgent,
      ...payload,
    });
  }

  hardenChartScriptableGuards() {
    if (typeof Chart === "undefined" || !Chart.defaults) return;

    const mark = "__kinjoScriptableGuard";
    const seen = new WeakSet();

    const walk = (node) => {
      if (!node || typeof node !== "object" || seen.has(node)) return;
      seen.add(node);

      if (typeof node._scriptable === "function" && !node._scriptable[mark]) {
        const original = node._scriptable.bind(node);
        const guarded = (key) =>
          typeof key === "string" ? original(key) : true;
        Object.defineProperty(guarded, mark, {
          value: true,
          enumerable: false,
        });
        node._scriptable = guarded;
      }

      Reflect.ownKeys(node).forEach((key) => {
        const value = node[key];
        if (value && typeof value === "object") walk(value);
      });
    };

    walk(Chart.defaults);
  }

  _probeChartRuntime(source = "runtime") {
    if (typeof Chart === "undefined") return false;
    try {
      const canvas = document.createElement("canvas");
      const probe = new Chart(canvas, {
        type: "bar",
        data: { labels: ["x"], datasets: [{ label: "x", data: [1] }] },
        options: {
          responsive: false,
          animation: false,
          plugins: { legend: { display: false } },
        },
      });
      probe.destroy();
      return true;
    } catch (error) {
      console.error("[AdminDashboard] Chart.js runtime probe failed:", error);
      this.reportChartRuntimeFailure("probe_failed", {
        source,
        errorMessage: error?.message || String(error),
      });
      return false;
    }
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
    const lastUpdatedLabel = this.getLastUpdatedElement();
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.classList.add("is-loading");
      refreshBtn.classList.remove("is-success");
      if (refreshText)
        refreshText.textContent =
          lang === "en" ? "Updating data..." : "جاري تحديث البيانات...";
      if (refreshIcon) refreshIcon.classList.add("spin");
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);

    try {
      const response = await fetch(this.apiEndpoint, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        credentials: "same-origin",
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      if (!response.ok)
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      const data = await response.json();
      this._lastData = data;
      this.renderDashboard(data);
      this.setState("success");
      this._waitForI18nThenRefresh();

      if (refreshBtn) {
        refreshBtn.classList.remove("is-loading");
        refreshBtn.classList.add("is-success");
        if (refreshText)
          refreshText.textContent =
            lang === "en" ? "Update Successful" : "تم التحديث بنجاح";
        if (refreshIcon) {
          refreshIcon.classList.remove("spin", "bi-arrow-clockwise");
          refreshIcon.classList.add("bi-check2");
        }

        const generatedAt = data.generated_at
          ? new Date(data.generated_at)
          : new Date();
        const timeStr = generatedAt.toLocaleTimeString(
          lang === "en" ? "en-US" : "ar-SA",
          { hour: "2-digit", minute: "2-digit" },
        );
        if (lastUpdatedLabel) {
          this._lastUpdatedAt = generatedAt;
          this._renderRelativeTime();
        }

        setTimeout(() => {
          refreshBtn.disabled = false;
          refreshBtn.classList.remove("is-success");
          if (refreshText)
            refreshText.textContent =
              lang === "en" ? "Update Data" : "تحديث البيانات";
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
      this._setErrorMessage(
        this.t(
          isTimeout ? "errors.request_timeout" : "errors.generic_error",
          isTimeout
            ? "Request timed out. Please try again."
            : "An error occurred. Please try again.",
        ),
      );
      this.setState("error");

      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.classList.remove("is-loading");
        if (refreshText)
          refreshText.textContent =
            lang === "en" ? "Update Data" : "تحديث البيانات";
        if (refreshIcon) {
          refreshIcon.classList.remove("spin", "bi-check2");
          refreshIcon.classList.add("bi-arrow-clockwise");
        }
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
    this.renderKPICards(
      normalized.kpis,
      normalized.kpi_trends,
      normalized.data_quality_reasons,
    );
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
    // Translate any data-i18n elements injected dynamically by this script
    window.AdminI18n?.translatePage?.();
  }

  /**
   * Map API response shape to internal normalized form.
   * The API returns { kpis, summary, system_overview, charts, alerts, recent_activity }.
   */
  normalizePayload(data) {
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    // kpis is now a flat dict provided directly by the API
    const kpis = data.kpis || {};
    const kpiTrends = data.kpi_trends || {};
    const dataQualityReasons = Array.isArray(data.data_quality_reasons)
      ? data.data_quality_reasons
      : [];

    const chartPayload = data.charts || {};
    const attendanceChart = {
      labels: Array.isArray(chartPayload.attendance)
        ? chartPayload.attendance.map((i) => i.date)
        : [],
      values: Array.isArray(chartPayload.attendance)
        ? chartPayload.attendance.map((i) => this.toNumber(i.value))
        : [],
    };

    const enrollment = chartPayload.enrollment || {};
    const submissionChart = {
      labels: Object.keys(enrollment).map((k) => {
        const i18nKey = ENROLLMENT_I18N[k];
        const fallback =
          (ENROLLMENT_FALLBACK[lang] || ENROLLMENT_FALLBACK.en)[k] || k;
        return i18nKey ? this.t(i18nKey, fallback) : fallback;
      }),
      values: Object.values(enrollment).map((v) => this.toNumber(v)),
    };

    const recentActivity =
      Array.isArray(data.recent_activity) && data.recent_activity.length > 0
        ? data.recent_activity
        : [];

    return {
      kpis,
      kpi_trends: kpiTrends,
      data_quality_reasons: dataQualityReasons,
      charts: {
        attendance: attendanceChart,
        data_submissions: submissionChart,
      },
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
      container.appendChild(
        this.createKPICard(
          config,
          this.sanitizeKPIValue(config.key, kpis[config.key]),
          (kpiTrends || {})[config.key],
          config.key === "data_quality_score" ? dataQualityReasons || [] : null,
        ),
      );
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
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    const desc = this._kpiDescription(config, lang);
    if (desc) card.title = desc; // native tooltip — keyboard + pointer accessible

    let { formattedValue, badgeHtml } = this.formatKPIValue(config, value);
    // A metric that could not be computed must not masquerade as a real value
    // (e.g. data quality with no eligible kindergartens showing "0%").
    if (trendMeta && trendMeta.measurable === false) {
      formattedValue = this.t("dashboard.value_unavailable", "Unavailable");
      badgeHtml = "";
    }

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

    // Modern touch: animate the numeric value counting up to its target.
    if (
      value !== null &&
      (config.format === "number" || config.format === "percentage")
    ) {
      this.animateCountUp(valueDiv, value, config.format, lang);
    }

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
    titleEl.textContent = this.t(
      `dashboard.${config.key}`,
      KPI_LABEL_FALLBACK[config.key] || config.key,
    );
    contentDiv.appendChild(titleEl);

    if (trendMeta && value !== null) {
      contentDiv.appendChild(this.createKPITrendRow(trendMeta));
      // Raw counts return no status row (neutral) — a "Good" badge without a
      // target is noise. Only judgment-bearing statuses render.
      const statusRow = this.createKPIStatusRow(trendMeta);
      if (statusRow) contentDiv.appendChild(statusRow);
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

    // No prior-period data (or metric unavailable): a "+635" here would be a
    // seed/baseline artifact, not a real trend. Show an explicit neutral note.
    const noBaseline =
      trendMeta.measurable === false || trendMeta.baseline_available === false;
    if (noBaseline) {
      row.className = "admin-kpi-card-trend admin-kpi-card-trend--flat";
      const icon = document.createElement("i");
      icon.className = "bi bi-dash-lg";
      icon.setAttribute("aria-hidden", "true");
      row.appendChild(icon);
      const text = document.createElement("span");
      text.textContent = this.t(
        "dashboard.trend_no_baseline",
        "No reliable prior-period comparison",
      );
      row.appendChild(text);
      return row;
    }

    row.className = `admin-kpi-card-trend admin-kpi-card-trend--${trendMeta.trend || "flat"}`;

    const icon = document.createElement("i");
    // Up/down are vertical arrows — direction is unaffected by RTL/LTR, so no .icon-directional here.
    icon.className =
      trendMeta.trend === "up"
        ? "bi bi-arrow-up-short"
        : trendMeta.trend === "down"
          ? "bi bi-arrow-down-short"
          : "bi bi-dash-lg";
    icon.setAttribute("aria-hidden", "true");
    row.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = this.formatTrendComparison(trendMeta);
    row.appendChild(text);

    return row;
  }

  formatTrendComparison(trendMeta) {
    const locale = window.KINJO_LANG === "ar" ? "ar-JO" : "en-US";
    const sign =
      trendMeta.trend === "up" ? "+" : trendMeta.trend === "down" ? "-" : "";
    let changeText;
    if (trendMeta.change_pct !== null && trendMeta.change_pct !== undefined) {
      changeText =
        sign +
        new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(
          Math.abs(trendMeta.change_pct),
        ) +
        "%";
    } else {
      changeText =
        sign +
        new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(
          Math.abs(trendMeta.change || 0),
        );
    }
    return this.t(
      "dashboard.trend_compare_period",
      `${changeText} vs. previous period`,
      { change: changeText },
    );
  }

  // Status meaning — icon + text, never color alone.
  // Returns null for "neutral" (raw counts) so no meaningless badge renders.
  createKPIStatusRow(trendMeta) {
    const status = trendMeta.status || "good";
    if (status === "neutral") return null;

    const row = document.createElement("div");
    row.className = `admin-kpi-card-status admin-kpi-card-status--${status}`;

    const iconByStatus = {
      good: "bi bi-check-circle-fill",
      warning: "bi bi-exclamation-triangle-fill",
      critical: "bi bi-x-octagon-fill",
      unavailable: "bi bi-dash-circle",
    };
    const labelByStatus = {
      good: this.t("dashboard.status_good", "Good"),
      warning: this.t("dashboard.status_warning", "Needs attention"),
      critical: this.t("dashboard.status_critical", "Critical"),
      unavailable: this.t("dashboard.status_unavailable", "Unavailable"),
    };

    const icon = document.createElement("i");
    icon.className = iconByStatus[status] || iconByStatus.good;
    icon.setAttribute("aria-hidden", "true");
    row.appendChild(icon);

    const text = document.createElement("span");
    text.textContent = labelByStatus[status] || labelByStatus.good;
    row.appendChild(text);

    return row;
  }

  // Data Quality card only: reasons behind the score, in a native <details> disclosure (free keyboard support).
  createDataQualityReasons(reasons) {
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    const details = document.createElement("details");
    details.className = "admin-kpi-dq-reasons";

    const summary = document.createElement("summary");
    summary.textContent = this.t(
      "dashboard.dq_view_issues",
      "View data issues",
    );
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
    improveLink.href = "/admin/daily-reports-organization";
    improveLink.textContent = this.t(
      "dashboard.dq_improve",
      "Improve data quality",
    );
    details.appendChild(improveLink);

    return details;
  }

  createKPIDrilldownLink(config) {
    const link = document.createElement("a");
    link.className = "admin-kpi-card-drilldown";
    link.href = config.drilldown;

    const text = document.createElement("span");
    text.textContent = this.t(
      config.drilldownLabelKey,
      KPI_LABEL_FALLBACK[config.key] || "View details",
    );
    link.appendChild(text);

    const chevron = document.createElement("i");
    chevron.className = "bi bi-chevron-right icon icon-directional";
    chevron.setAttribute("aria-hidden", "true");
    link.appendChild(chevron);

    return link;
  }

  formatKPIValue(config, value) {
    // Null signals "data unavailable" — show em-dash instead of zero
    if (value === null || value === undefined)
      return { formattedValue: "—", badgeHtml: "" };

    const locale = window.KINJO_LANG === "ar" ? "ar-JO" : "en-US";
    let formattedValue = String(value);
    let badgeHtml = "";

    if (config.format === "number") {
      formattedValue = new Intl.NumberFormat(locale).format(value);
    } else if (config.format === "percentage") {
      formattedValue = new Intl.NumberFormat(locale, {
        style: "percent",
        maximumFractionDigits: 1,
      }).format(value / 100);
      if (config.key === "data_quality_score") {
        const { cls, key, fb } =
          value >= 80
            ? { cls: "dq-badge-good", key: "dashboard.dq_good", fb: "Good" }
            : value >= 60
              ? {
                  cls: "dq-badge-average",
                  key: "dashboard.dq_average",
                  fb: "Average",
                }
              : { cls: "dq-badge-low", key: "dashboard.dq_low", fb: "Low" };
        badgeHtml = `<span class="dq-badge ${escapeHtml(cls)}">${escapeHtml(this.t(key, fb))}</span>`;
      }
    }

    return { formattedValue, badgeHtml };
  }

  // ── Charts ────────────────────────────────────────────────────────────────

  renderCharts(charts) {
    if (typeof Chart === "undefined") return;
    const attendanceCtx = document.getElementById("attendance-chart");
    const submissionsCtx = document.getElementById("enrollment-status-chart");

    this.clearChartEmptyState(attendanceCtx);
    this.clearChartEmptyState(submissionsCtx);

    // Re-check runtime health before each draw cycle when probing is enabled.
    if (
      this.chartRuntimeProbeEnabled &&
      !this.chartRuntimeBroken &&
      !this._probeChartRuntime("render-cycle")
    ) {
      this.chartRuntimeBroken = true;
    }

    if (this.chartRuntimeBroken) {
      if (attendanceCtx) {
        this.showChartEmpty(
          attendanceCtx,
          this.t(
            "dashboard.no_attendance_data",
            "No attendance data for the selected period",
          ),
        );
      }
      if (submissionsCtx) {
        this.showChartEmpty(
          submissionsCtx,
          this.t(
            "dashboard.no_enrollment_data",
            "No enrollment data for the selected period",
          ),
        );
      }
      return;
    }

    if (
      charts.attendance &&
      charts.attendance.labels &&
      charts.attendance.labels.length
    ) {
      try {
        this.renderAttendanceChart(charts.attendance);
      } catch (error) {
        console.error("[AdminDashboard] attendance chart render error:", error);
        this.chartRuntimeBroken = true;
        this.reportChartRuntimeFailure("attendance_render_failed", {
          errorMessage: error?.message || String(error),
        });
        if (attendanceCtx) {
          this.showChartEmpty(
            attendanceCtx,
            this.t(
              "dashboard.no_attendance_data",
              "No attendance data for the selected period",
            ),
          );
        }
      }
    } else if (attendanceCtx) {
      this.showChartEmpty(
        attendanceCtx,
        this.t(
          "dashboard.no_attendance_data",
          "No attendance data for the selected period",
        ),
      );
    }

    if (
      charts.data_submissions &&
      charts.data_submissions.labels &&
      charts.data_submissions.labels.length
    ) {
      try {
        this.renderSubmissionsChart(charts.data_submissions);
      } catch (error) {
        console.error(
          "[AdminDashboard] submissions chart render error:",
          error,
        );
        this.chartRuntimeBroken = true;
        this.reportChartRuntimeFailure("submissions_render_failed", {
          errorMessage: error?.message || String(error),
        });
        if (submissionsCtx) {
          this.showChartEmpty(
            submissionsCtx,
            this.t(
              "dashboard.no_enrollment_data",
              "No enrollment data for the selected period",
            ),
          );
        }
      }
    } else if (submissionsCtx) {
      this.showChartEmpty(
        submissionsCtx,
        this.t(
          "dashboard.no_enrollment_data",
          "No enrollment data for the selected period",
        ),
      );
    }
  }

  showChartEmpty(canvas, message) {
    const container = canvas.closest(".admin-card-body");
    if (!container) return;
    canvas.style.display = "none";
    container.querySelector(".dashboard-chart-empty-state")?.remove();
    const empty = document.createElement("div");
    empty.className =
      "agency-alert agency-alert--info dashboard-chart-empty-state";
    empty.textContent = message;
    container.appendChild(empty);
  }

  clearChartEmptyState(canvas) {
    if (!canvas) return;
    const container = canvas.closest(".admin-card-body");
    if (!container) return;
    canvas.style.display = "";
    container.querySelector(".dashboard-chart-empty-state")?.remove();
  }

  /**
   * Injects an accessible, collapsible "About this dashboard" reference that
   * explains every section of the page. The template cannot be edited in this
   * pass, so the explanation is added to the DOM at runtime, right after the
   * existing "How to use" guide. Built with semantic <details>/<summary> for
   * free keyboard support and screen-reader disclosure.
   */
  renderComponentGuide() {
    if (document.getElementById("admin-component-guide")) return;
    // Prefer the legacy "How to use" guide as the anchor when present; otherwise
    // fall back to the KPI-cards list so the reference always renders instead of
    // silently no-opping (the template ships no .admin-dashboard-guide element).
    const legacyGuide = document.querySelector(".admin-dashboard-guide");
    const anchor = legacyGuide || document.getElementById("kpi-cards");
    if (!anchor) return;
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";

    const COMPONENTS = [
      {
        key: "kpis",
        title: { en: "KPI cards", ar: "بطاقات المؤشرات" },
        desc: {
          en: "Seven headline metrics: total users, users logged in today, total & active kindergartens, reports submitted, pending reports, and data-quality score.",
          ar: "سبعة مؤشرات رئيسية: إجمالي المستخدمين، المستخدمون الذين سجلوا الدخول اليوم، إجمالي والحضانات النشطة، التقارير المقدّمة، التقارير المعلّقة، ودرجة جودة البيانات.",
        },
      },
      {
        key: "alerts",
        title: { en: "System alerts", ar: "تنبيهات النظام" },
        desc: {
          en: "Items needing attention, ordered by severity: pending enrolments, recent incidents, and licence expiries.",
          ar: "بنود تحتاج متابعة مرتّبة حسب الخطورة: طلبات التسجيل المعلّقة، الحوادث الأخيرة، وانتهاء التراخيص.",
        },
      },
      {
        key: "activity",
        title: { en: "Daily attendance chart", ar: "مخطط الحضور اليومي" },
        desc: {
          en: "Line chart of daily attendance over the selected period so you can spot engagement trends.",
          ar: "مخطط خطي لحضور يومي خلال الفترة المحددة لملاحظة اتجاهات التفاعل.",
        },
      },
      {
        key: "enrollment",
        title: { en: "Enrollment status chart", ar: "مخطط حالة التسجيل" },
        desc: {
          en: "Bar chart of enrolment applications by stage, revealing where pending workload sits.",
          ar: "مخطط أعمدة لطلبات التسجيل حسب المرحلة، يوضح حجم العمل المعلّق.",
        },
      },
      {
        key: "feed",
        title: { en: "Recent activity", ar: "النشاطات الحديثة" },
        desc: {
          en: "Audit trail of the latest administrative actions with the actor and timestamp.",
          ar: "سجل تدقيق لآخر الإجراءات الإدارية مع الفاعل والوقت.",
        },
      },
      {
        key: "actions",
        title: { en: "Quick actions", ar: "الإجراءات السريعة" },
        desc: {
          en: "Shortcuts to the most common tasks: manage users, send messages, view analytics, manage data.",
          ar: "اختصارات لأكثر المهام شيوعاً: إدارة المستخدمين، إرسال رسالة، عرض التحليلات، إدارة البيانات.",
        },
      },
      {
        key: "agency",
        title: { en: "Official agency reports", ar: "تقارير الجهات الرسمية" },
        desc: {
          en: "Aggregated, privacy-controlled reports generated for external government stakeholders.",
          ar: "تقارير مجمّعة وخاضعة لضوابط الخصوصية موجّهة للجهات الحكومية الخارجية.",
        },
      },
    ];

    const section = document.createElement("section");
    section.id = "admin-component-guide";
    section.className =
      "admin-component-guide agency-reports-dashboard-section";
    section.setAttribute("aria-labelledby", "admin-component-guide-title");

    const details = document.createElement("details");
    details.className = "admin-component-guide-details";

    const summary = document.createElement("summary");
    summary.id = "admin-component-guide-title";
    summary.textContent =
      lang === "en" ? "About this dashboard" : "حول لوحة التحكم";
    details.appendChild(summary);

    const intro = document.createElement("p");
    intro.className = "admin-component-guide-intro";
    intro.textContent =
      lang === "en"
        ? "Each section below is explained so you can read the page with confidence:"
        : "يُشرح كل قسم أدناه لتتمكّن من قراءة الصفحة بثقة:";
    details.appendChild(intro);

    const list = document.createElement("ul");
    list.className = "admin-component-guide-list";
    COMPONENTS.forEach((c) => {
      const li = document.createElement("li");
      const h = document.createElement("h3");
      h.className = "admin-component-guide-item-title";
      h.textContent = c.title[lang];
      const p = document.createElement("p");
      p.textContent = c.desc[lang];
      li.appendChild(h);
      li.appendChild(p);
      list.appendChild(li);
    });
    details.appendChild(list);
    section.appendChild(details);

    // After the legacy guide when present, else just before the KPI cards.
    anchor.insertAdjacentElement(
      legacyGuide ? "afterend" : "beforebegin",
      section,
    );
  }

  // ── Relative "updated" timestamp ─────────────────────────────────────────

  startRelativeTimeTicker() {
    if (this._relativeTickerId) clearTimeout(this._relativeTickerId);
    // Adaptive cadence keeps the "seconds ago" reading fresh without per-second
    // churn: every 5s in the first minute, 30s within the hour, then a minute.
    const tick = () => {
      this._renderRelativeTime();
      const sec = this._lastUpdatedAt
        ? Math.floor((Date.now() - this._lastUpdatedAt.getTime()) / 1000)
        : 0;
      const delay = sec < 60 ? 5000 : sec < 3600 ? 30000 : 60000;
      this._relativeTickerId = setTimeout(tick, delay);
    };
    this._relativeTickerId = setTimeout(tick, 5000);
  }

  _renderRelativeTime() {
    const el = this.getLastUpdatedElement();
    if (!el || !this._lastUpdatedAt) return;
    const sec = Math.max(
      0,
      Math.floor((Date.now() - this._lastUpdatedAt.getTime()) / 1000),
    );
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    if (sec < 5) {
      el.textContent = lang === "en" ? "Updated just now" : "تم التحديث الآن";
      return;
    }
    const locale = lang === "en" ? "en-US" : "ar-JO";
    const prefix = lang === "en" ? "Updated " : "تم التحديث ";
    let rel;
    try {
      // Intl handles pluralization (second/seconds, ثانية/ثانيتين/ثوانٍ, the
      // Arabic dual) and locale numerals (Arabic-Indic in ar-JO) natively.
      const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
      if (sec < 60) rel = rtf.format(-sec, "second");
      else if (sec < 3600) rel = rtf.format(-Math.floor(sec / 60), "minute");
      else rel = rtf.format(-Math.floor(sec / 3600), "hour");
    } catch (e) {
      rel = lang === "en" ? `${sec} seconds ago` : `قبل ${sec} ثانية`;
    }
    el.textContent = prefix + rel;
  }

  getLastUpdatedElement() {
    return (
      document.getElementById("last-updated-time-value") ||
      document.getElementById("last-updated-time")
    );
  }

  // ── KPI helper: accessible description for tooltips ──────────────────────

  _kpiDescription(config, lang) {
    const MAP = {
      total_users: {
        en: "All user accounts in the system.",
        ar: "جميع حسابات المستخدمين في النظام.",
      },
      active_users: {
        en: "Users who signed in today.",
        ar: "المستخدمون الذين سجّلوا دخولهم اليوم.",
      },
      total_kindergartens: {
        en: "Every kindergarten on record.",
        ar: "كل حضانة مسجّلة في النظام.",
      },
      active_kindergartens: {
        en: "Kindergartens currently marked active.",
        ar: "الحضانات المفعّلة حالياً.",
      },
      total_submissions: {
        en: "Daily reports submitted in the selected period.",
        ar: "التقارير اليومية المقدّمة خلال الفترة المحددة.",
      },
      pending_submissions: {
        en: "Daily reports awaiting review.",
        ar: "التقارير اليومية بانتظار المراجعة.",
      },
      data_quality_score: {
        en: "Share of active kindergartens that reported in the last 7 days.",
        ar: "نسبة الحضانات النشطة التي قدّمت تقريراً خلال آخر 7 أيام.",
      },
    };
    const m = MAP[config.key];
    return m ? m[lang] : "";
  }

  /**
   * Lightweight requestAnimationFrame count-up for KPI values. Always finishes
   * on the exact locale-formatted string so screen readers and layouts stay
   * correct even if the animation is interrupted.
   */
  animateCountUp(el, target, format, lang) {
    if (typeof target !== "number" || !Number.isFinite(target)) return;
    // Respect users who requested reduced motion — the final value is already
    // set on the element, so we simply skip the animation entirely (WCAG 2.3.3).
    if (
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    const finalText = el.textContent;
    const locale = lang === "en" ? "en-US" : "ar-JO";
    const start =
      typeof performance !== "undefined" ? performance.now() : Date.now();
    const duration = 700;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = target * eased;
      el.textContent =
        format === "percentage"
          ? new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(
              current,
            ) + "%"
          : new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(
              Math.round(current),
            );
      if (t < 1) requestAnimationFrame(step);
      else el.textContent = finalText; // exact locale-correct final value
    };
    try {
      requestAnimationFrame(step);
    } catch (e) {
      el.textContent = finalText;
    }
  }

  renderAttendanceChart(data) {
    const ctx = document.getElementById("attendance-chart");
    if (!ctx) return;
    this.clearChartEmptyState(ctx);
    // Accessibility: give the canvas an accessible name + role.
    ctx.setAttribute("role", "img");
    ctx.setAttribute(
      "aria-label",
      window.KINJO_LANG === "en"
        ? "Daily attendance chart showing recorded attendance by date"
        : "مخطط الحضور اليومي يوضح سجلات الحضور حسب التاريخ",
    );
    this.charts.attendance?.destroy();
    const context = ctx.getContext("2d");
    const gradient = context
      ? (() => {
          const g = context.createLinearGradient(0, 0, 0, 220);
          g.addColorStop(0, "rgba(31, 94, 71, 0.28)");
          g.addColorStop(1, "rgba(31, 94, 71, 0.02)");
          return g;
        })()
      : "rgba(31, 94, 71, 0.1)";
    this.charts.attendance = new Chart(ctx, {
      type: "line",
      data: {
        labels: safeChartData(data.labels),
        datasets: [
          {
            label:
              window.KINJO_LANG === "en"
                ? "Recorded Attendance"
                : ATTENDANCE_CHART_LABELS["Recorded Attendance"],
            data: safeChartData(data.values),
            borderColor: "#4F46E5",
            backgroundColor: gradient,
            tension: 0.4,
            fill: true,
            pointRadius: 4,
            pointHoverRadius: 6,
            pointBackgroundColor: "#4F46E5",
            pointBorderColor: "#fff",
            pointBorderWidth: 2,
            borderWidth: 2.5,
          },
        ],
      },
      options: {
        animation: { duration: 600, easing: "easeOutQuart" },
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f8fafc",
            bodyColor: "#f8fafc",
            padding: 10,
            cornerRadius: 8,
          },
        },
        scales: {
          x: { ticks: { color: "#6c757d" }, grid: { display: false } },
          y: {
            beginAtZero: true,
            ticks: { precision: 0, color: "#6c757d" },
            grid: { color: "rgba(0,0,0,0.06)" },
          },
        },
      },
    });
  }

  renderSubmissionsChart(data) {
    const ctx = document.getElementById("enrollment-status-chart");
    if (!ctx) return;
    this.clearChartEmptyState(ctx);
    // Accessibility: give the canvas an accessible name + role.
    ctx.setAttribute("role", "img");
    ctx.setAttribute(
      "aria-label",
      window.KINJO_LANG === "en"
        ? "Enrollment status chart showing distribution of application statuses"
        : "مخطط حالة التسجيل يوضح توزيع حالات الطلبات",
    );
    this.charts.dataSubmissions?.destroy();
    const palette = [
      "#0d6efd",
      "#198754",
      "#ffc107",
      "#dc3545",
      "#6c757d",
      "#0dcaf0",
    ];
    this.charts.dataSubmissions = new Chart(ctx, {
      type: "bar",
      data: {
        labels: safeChartData(data.labels),
        datasets: [
          {
            label: this.t("dashboard.enrollment_status", "Enrollment Status"),
            data: safeChartData(data.values),
            backgroundColor: safeChartData(data.labels).map(
              (_, i) => palette[i % palette.length],
            ),
            borderWidth: 0,
            borderRadius: 6,
          },
        ],
      },
      options: {
        indexAxis: "y",
        animation: { duration: 600, easing: "easeOutQuart" },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(17,24,39,0.92)",
            titleColor: "#f8fafc",
            bodyColor: "#f8fafc",
            padding: 10,
            cornerRadius: 8,
            callbacks: {
              label: (ctx) => ` ${ctx.parsed.x.toLocaleString()}`,
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0 },
            grid: { color: "rgba(0,0,0,0.06)" },
          },
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
      container.appendChild(
        this.createEmptyState(
          "dashboard.no_recent_activity",
          "No recent activity",
          "dashboard.no_activity_hint",
          "Add users or monitor operations to see activity here",
          "bi-clock-history",
          "dashboard.manage_users",
          "Manage Users",
          "/admin/users",
        ),
      );
      return;
    }
    activities.forEach((a) =>
      container.appendChild(this.createActivityItem(a)),
    );
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
      (message.includes("تسجيل دخول") ||
        message.includes("User login") ||
        message.includes("login"))
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
    badge.textContent =
      this.formatStatus(activity.status) ||
      (lang === "en" ? "Success" : "مكتمل");

    titleRow.appendChild(title);
    titleRow.appendChild(badge);

    // Meta Row
    const metaRow = document.createElement("div");
    metaRow.className = "activity-meta-row";

    const actor = document.createElement("span");
    actor.className = "activity-actor";
    const actorIcon = document.createElement("i");
    actorIcon.className = "bi bi-person-fill";
    actor.append(
      actorIcon,
      ` ${activity.user_name || this.t("dashboard.system_actor", "System")}`,
    );

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
      const categoryBadge = document.createElement("span");
      categoryBadge.className = "activity-category-badge";
      const categoryIcon = document.createElement("i");
      categoryIcon.className = "bi bi-folder2";
      categoryBadge.append(categoryIcon, ` ${moduleName}`);
      categoryRow.appendChild(categoryBadge);
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
      container.appendChild(
        this.createEmptyState(
          "dashboard.no_alerts",
          "No active alerts",
          "dashboard.no_alerts_hint",
          "You'll be notified when important system events occur",
          "bi-bell-slash",
        ),
      );
      return;
    }
    alerts.forEach((a) => container.appendChild(this.createAlertItem(a)));
  }

  createAlertItem(alert) {
    const lang = window.KINJO_LANG === "en" ? "en" : "ar";
    const message = alert[`message_${lang}`] || alert.message || "";
    return this._createFeedItem({
      wrapperClass: `admin-alert-item admin-alert-${alert.severity || "info"}`,
      iconWrapClass: "admin-alert-icon",
      iconClass: this.getAlertIcon(alert.severity),
      contentClass: "admin-alert-content",
      msgClass: "admin-alert-message",
      timeClass: "admin-alert-time",
      message,
      timestamp: alert.timestamp,
      role: "listitem",
    });
  }

  // Shared DOM builder for activity and alert feed items — eliminates duplication.
  _createFeedItem({
    wrapperClass,
    iconWrapClass,
    iconClass,
    contentClass,
    msgClass,
    timeClass,
    message,
    timestamp,
    role,
  }) {
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

  createEmptyState(
    primaryKey,
    primaryFallback,
    hintKey,
    hintFallback,
    iconClass = "bi-inbox",
    ctaKey = null,
    ctaFallback = null,
    ctaHref = null,
  ) {
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
    const diff = Math.max(0, Date.now() - time.getTime());
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(diff / 3600000);
    const days = Math.floor(diff / 86400000);
    if (minutes < 1) return this.t("common.just_now", "just now");
    if (minutes < 60)
      return this.t("dashboard.time_minutes_ago", `${minutes} minutes ago`, {
        count: this.formatNumber(minutes),
      });
    if (hours < 24)
      return this.t("dashboard.time_hours_ago", `${hours} hours ago`, {
        count: this.formatNumber(hours),
      });
    return this.t("dashboard.time_days_ago", `${days} days ago`, {
      count: this.formatNumber(days),
    });
  }

  t(key, fallback = "", params = {}) {
    const i18n = window.AdminI18n;
    if (i18n && typeof i18n.translate === "function")
      return i18n.translate(key, fallback, params);
    return fallback || key;
  }

  getActivityIcon(type) {
    return (
      {
        user_login: "bi bi-box-arrow-in-right",
        user_logout: "bi bi-box-arrow-left",
        data_submit: "bi bi-upload",
        user_create: "bi bi-person-plus-fill",
        system_update: "bi bi-gear-fill",
      }[type] || "bi bi-info-circle-fill"
    );
  }

  getAlertIcon(severity) {
    // get_admin_dashboard's alert builders emit severity="error" (expired
    // licenses, >5 incidents/week) — this map had no "error" key at all, so
    // those alerts silently fell through to the generic info-circle icon
    // instead of a severity-appropriate one.
    return (
      {
        critical: "bi bi-exclamation-triangle-fill",
        error: "bi bi-exclamation-triangle-fill",
        warning: "bi bi-exclamation-circle-fill",
        info: "bi bi-info-circle-fill",
        success: "bi bi-check-circle-fill",
      }[severity] || "bi bi-info-circle-fill"
    );
  }

  // ── Auto Refresh ──────────────────────────────────────────────────────────

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.intervalId = setInterval(
      () => this.loadDashboardData(),
      this.refreshInterval,
    );
  }

  stopAutoRefresh() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  destroy() {
    this.stopAutoRefresh();
    if (this._relativeTickerId) clearTimeout(this._relativeTickerId);
    document
      .getElementById("refresh-dashboard")
      ?.removeEventListener("click", this._listeners.refresh);
    document
      .getElementById("retry-dashboard")
      ?.removeEventListener("click", this._listeners.retry);
    document
      .getElementById("autoRefreshCheck")
      ?.removeEventListener("change", this._listeners.autoRefreshToggle);
    document.removeEventListener(
      "visibilitychange",
      this._listeners.visibility,
    );
    Object.values(this.charts).forEach((c) => c?.destroy());
    this.charts = {};
  }
}

window.adminDashboard = new AdminDashboard();
window.AdminDashboard = AdminDashboard;
