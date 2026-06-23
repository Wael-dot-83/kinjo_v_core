/**
 * KinJo Admin Dashboard — Arabic RTL
 * Fetches /api/admin/dashboard and renders all sections.
 * safeChartData() is provided globally by chart_utils.js.
 */

/* ── XSS guard ──────────────────────────────────────────────────────────── */
function esc(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* ── i18n shim ──────────────────────────────────────────────────────────── */
function t(key, fallback) {
  const i18n = window.AdminI18n;
  if (i18n && typeof i18n.translate === "function") return i18n.translate(key, fallback || key);
  return fallback || key;
}

/* ── Number / date helpers ──────────────────────────────────────────────── */
function fmtNum(n) {
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  const locale = t("common.locale", "ar-JO");
  return new Intl.NumberFormat(locale).format(v);
}

function fmtDate(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  if (isNaN(d)) return "";
  return d.toLocaleString("ar-JO", { dateStyle: "short", timeStyle: "short" });
}

function fmtTimeAgo(ts) {
  if (!ts) return "";
  const diff = Date.now() - new Date(ts).getTime();
  if (isNaN(diff)) return "";
  const m = Math.floor(diff / 60000);
  const h = Math.floor(diff / 3600000);
  const d = Math.floor(diff / 86400000);
  if (m < 1)  return "الآن";
  if (m < 60) return `منذ ${m} دقيقة`;
  if (h < 24) return `منذ ${h} ساعة`;
  return `منذ ${d} يوم`;
}

function toNum(v) { const n = Number(v); return Number.isFinite(n) ? n : 0; }

/* ══════════════════════════════════════════════════════════════════════════
   MAIN DASHBOARD CLASS
══════════════════════════════════════════════════════════════════════════ */
class KinjoDashboard {
  constructor() {
    this.endpoint   = "/api/admin/dashboard";
    this.interval   = 300_000; // 5 min
    this.intervalId = null;
    this.charts     = {};
    this.busy       = false;

    document.addEventListener("DOMContentLoaded", () => this._boot());
  }

  /* ── Bootstrap ────────────────────────────────────────────────────────── */
  _boot() {
    this._initClock();
    this._bindButtons();
    this._load();
    this._startRefresh();

    document.addEventListener("visibilitychange", () =>
      document.hidden ? this._stopRefresh() : this._startRefresh());
  }

  _initClock() {
    const el = document.getElementById("kd-today-date");
    if (!el) return;
    const render = () => {
      el.textContent = new Date().toLocaleDateString("ar-JO", {
        weekday: "long", year: "numeric", month: "long", day: "numeric"
      });
    };
    render();
  }

  _bindButtons() {
    const refresh = document.getElementById("kd-refresh-btn");
    const retry   = document.getElementById("kd-retry-btn");
    if (refresh) refresh.addEventListener("click", () => this._load());
    if (retry)   retry.addEventListener("click",   () => this._load());
  }

  /* ── Data fetch ───────────────────────────────────────────────────────── */
  async _load() {
    if (this.busy) return;
    this.busy = true;
    this._showLoading();
    try {
      const res = await fetch(this.endpoint, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      this._render(raw);
      this._showContent();
      const ts = document.getElementById("kd-last-updated");
      if (ts) ts.textContent = "آخر تحديث: " + new Date().toLocaleTimeString("ar-JO");
    } catch (err) {
      console.error("[KinjoDashboard]", err);
      this._showError(err.message);
    } finally {
      this.busy = false;
    }
  }

  /* ── Orchestrate rendering ────────────────────────────────────────────── */
  _render(raw) {
    const d = this._normalize(raw);
    this._renderKPIs(d.kpis, d.summary);
    this._renderCharts(d.charts);
    this._renderActivity(d.activity);
    this._renderAlerts(d.alerts);
    this._renderHealth(d.health);
    this._updateCounts(d);
  }

  /* ── Normalize API payload ────────────────────────────────────────────── */
  _normalize(raw) {
    const s = raw.summary        || {};
    const o = raw.system_overview || {};
    const charts = raw.charts    || {};
    const alerts = Array.isArray(raw.alerts) ? raw.alerts : [];

    /* KPI cards — use explicit kpis block if present, else derive */
    const kpis = raw.kpis || {};
    const totalUsers     = toNum(kpis.total_users    || o.total_users);
    const activeToday    = toNum(kpis.active_users   || s.attendance_today);
    const totalKGs       = toNum(kpis.total_kindergartens  || o.total_kindergartens);
    const activeKGs      = toNum(kpis.active_kindergartens || o.active_kindergartens);
    const pendingApps    = toNum(kpis.total_submissions    || s.pending_applications);
    const pendingReports = toNum(kpis.pending_submissions  || s.pending_daily_reports);
    const incidents      = toNum(s.recent_incidents);
    const attRate        = toNum(kpis.data_quality_score   || s.attendance_rate);

    /* Charts */
    const activityChart = charts.user_activity || {
      labels: (charts.attendance || []).map(x => x.date),
      values: (charts.attendance || []).map(x => toNum(x.value)),
    };
    const enrollChart = charts.data_submissions || {
      labels: Object.keys(charts.enrollment || {}),
      values: Object.values(charts.enrollment || {}).map(toNum),
    };

    /* Activity feed */
    const activity = Array.isArray(raw.recent_activity)
      ? raw.recent_activity
      : alerts.slice(0, 6).map(a => ({
          type: "system_update",
          message: a.title || a.message || "",
          timestamp: a.timestamp,
        }));

    /* System health indicators */
    const health = raw.system_health || [
      { label: "قاعدة البيانات",     status: "ok",      icon: "bi-database-fill-check" },
      { label: "خدمة المصادقة",      status: "ok",      icon: "bi-shield-fill-check"   },
      { label: "خادم الويب",         status: "ok",      icon: "bi-server"               },
      { label: "تدفق الإشعارات",     status: pendingReports > 50 ? "warn" : "ok", icon: "bi-bell-fill" },
    ];

    return {
      kpis: { totalUsers, activeToday, totalKGs, activeKGs, pendingApps, pendingReports, incidents, attRate },
      summary: s,
      charts: { activity: activityChart, enrollment: enrollChart },
      activity,
      alerts,
      health,
    };
  }

  /* ══════════════════════════════════════════════════════════════════════
     SECTION: KPI Cards
  ══════════════════════════════════════════════════════════════════════ */
  _renderKPIs(kpis, summary) {
    const grid = document.getElementById("kd-kpi-grid");
    if (!grid) return;

    const cards = [
      {
        key:   "totalUsers",
        label: "إجمالي المستخدمين",
        value: fmtNum(kpis.totalUsers),
        icon:  "bi-people-fill",
        color: "blue",
        link:  "/admin/users",
        trend: null,
      },
      {
        key:   "activeToday",
        label: "مستخدمون نشطون اليوم",
        value: fmtNum(kpis.activeToday),
        icon:  "bi-person-check-fill",
        color: "green",
        link:  "/admin/audit-logs",
        trend: null,
      },
      {
        key:   "totalKGs",
        label: "إجمالي الروضات",
        value: fmtNum(kpis.totalKGs),
        icon:  "bi-buildings-fill",
        color: "teal",
        link:  "/admin/kg-overview",
        trend: null,
      },
      {
        key:   "activeKGs",
        label: "الروضات النشطة",
        value: fmtNum(kpis.activeKGs),
        icon:  "bi-house-check-fill",
        color: "cyan",
        link:  "/admin/kg-overview",
        trend: null,
      },
      {
        key:   "pendingApps",
        label: "طلبات التسجيل المعلقة",
        value: fmtNum(kpis.pendingApps),
        icon:  "bi-file-earmark-person-fill",
        color: kpis.pendingApps > 0 ? "orange" : "green",
        link:  "/admin/analytics",
        trend: kpis.pendingApps > 0 ? "up" : null,
        urgent: kpis.pendingApps > 10,
      },
      {
        key:   "pendingReports",
        label: "تقارير يومية معلقة",
        value: fmtNum(kpis.pendingReports),
        icon:  "bi-clock-history",
        color: kpis.pendingReports > 0 ? "red" : "green",
        link:  "/admin/analytics/daily-reports",
        trend: kpis.pendingReports > 0 ? "up" : null,
        urgent: kpis.pendingReports > 5,
      },
      {
        key:   "incidents",
        label: "حوادث (آخر 7 أيام)",
        value: fmtNum(kpis.incidents),
        icon:  "bi-exclamation-triangle-fill",
        color: kpis.incidents > 0 ? "orange" : "green",
        link:  "/admin/reports/incidents",
        trend: kpis.incidents > 3 ? "up" : null,
      },
      {
        key:   "attRate",
        label: "معدل الحضور",
        value: `${kpis.attRate.toFixed(1)}%`,
        icon:  "bi-graph-up-arrow",
        color: kpis.attRate >= 80 ? "green" : kpis.attRate >= 60 ? "orange" : "red",
        link:  "/admin/analytics",
        trend: kpis.attRate >= 80 ? "good" : "warn",
      },
    ];

    grid.innerHTML = "";
    cards.forEach(c => grid.appendChild(this._buildKPICard(c)));

    const ts = document.getElementById("kd-kpi-timestamp");
    if (ts) ts.textContent = new Date().toLocaleTimeString("ar-JO");
  }

  _buildKPICard(c) {
    const el = document.createElement("a");
    el.className = `kd-kpi-card kd-kpi-${c.color}${c.urgent ? " kd-kpi-urgent" : ""}`;
    el.href = c.link || "#";
    el.setAttribute("role", "listitem");
    el.setAttribute("aria-label", `${c.label}: ${c.value}`);

    let trendHtml = "";
    if (c.trend === "up")   trendHtml = `<span class="kd-kpi-trend kd-trend-up"  aria-label="مرتفع"><i class="bi bi-arrow-up-short" aria-hidden="true"></i></span>`;
    if (c.trend === "warn") trendHtml = `<span class="kd-kpi-trend kd-trend-warn" aria-label="تحذير"><i class="bi bi-arrow-down-short" aria-hidden="true"></i></span>`;
    if (c.trend === "good") trendHtml = `<span class="kd-kpi-trend kd-trend-good" aria-label="جيد"><i class="bi bi-check-lg" aria-hidden="true"></i></span>`;

    el.innerHTML = `
      <div class="kd-kpi-icon-wrap" aria-hidden="true">
        <i class="bi ${esc(c.icon)}"></i>
      </div>
      <div class="kd-kpi-body">
        <div class="kd-kpi-value">${esc(c.value)}${trendHtml}</div>
        <div class="kd-kpi-label">${esc(c.label)}</div>
      </div>
      <i class="bi bi-chevron-left kd-kpi-arrow" aria-hidden="true"></i>
    `;
    return el;
  }

  /* ══════════════════════════════════════════════════════════════════════
     SECTION: Charts
  ══════════════════════════════════════════════════════════════════════ */
  _renderCharts({ activity, enrollment }) {
    if (typeof Chart === "undefined") return;

    const rtlFont = "'Cairo', 'Noto Sans Arabic', sans-serif";

    Chart.defaults.font.family = rtlFont;
    Chart.defaults.responsive  = true;
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.plugins.legend.position = "bottom";

    this._buildLineChart("kd-chart-activity", activity,  "المستخدمون النشطون", "#2563eb");
    this._buildBarChart ("kd-chart-enrollment", enrollment, "الطلبات",           "#0891b2");
  }

  _buildLineChart(canvasId, data, label, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (this.charts[canvasId]) this.charts[canvasId].destroy();
    this.charts[canvasId] = new Chart(ctx, {
      type: "line",
      data: {
        labels: safeChartData(data.labels),
        datasets: [{
          label,
          data: safeChartData(data.values),
          borderColor: color,
          backgroundColor: color + "22",
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, labels: { font: { family: "'Cairo', sans-serif" } } },
          tooltip: { mode: "index", intersect: false },
        },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0, font: { family: "'Cairo', sans-serif" } } },
          x: { ticks: { font: { family: "'Cairo', sans-serif" } } },
        },
      },
    });
  }

  _buildBarChart(canvasId, data, label, color) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    if (this.charts[canvasId]) this.charts[canvasId].destroy();
    this.charts[canvasId] = new Chart(ctx, {
      type: "bar",
      data: {
        labels: safeChartData(data.labels),
        datasets: [{
          label,
          data: safeChartData(data.values),
          backgroundColor: color + "cc",
          borderColor: color,
          borderWidth: 1,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, labels: { font: { family: "'Cairo', sans-serif" } } },
        },
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0, font: { family: "'Cairo', sans-serif" } } },
          x: { ticks: { font: { family: "'Cairo', sans-serif" } } },
        },
      },
    });
  }

  /* ══════════════════════════════════════════════════════════════════════
     SECTION: Activity Feed
  ══════════════════════════════════════════════════════════════════════ */
  _renderActivity(items) {
    const feed = document.getElementById("kd-activity-feed");
    if (!feed) return;

    if (!items || items.length === 0) {
      feed.innerHTML = `<div class="kd-empty"><i class="bi bi-inbox" aria-hidden="true"></i><p>لا يوجد نشاط حديث</p></div>`;
      return;
    }

    feed.innerHTML = "";
    items.slice(0, 8).forEach(item => {
      const el = document.createElement("div");
      el.className = "kd-feed-item";
      el.innerHTML = `
        <div class="kd-feed-icon ${this._activityColor(item.type)}" aria-hidden="true">
          <i class="bi ${this._activityIcon(item.type)}"></i>
        </div>
        <div class="kd-feed-body">
          <p class="kd-feed-msg">${esc(item.message || "")}</p>
          <time class="kd-feed-time" datetime="${esc(item.timestamp || "")}">${fmtTimeAgo(item.timestamp)}</time>
        </div>
      `;
      feed.appendChild(el);
    });
  }

  _activityIcon(type) {
    const map = {
      user_login:    "bi-box-arrow-in-right",
      user_logout:   "bi-box-arrow-left",
      user_create:   "bi-person-plus-fill",
      data_submit:   "bi-cloud-upload-fill",
      system_update: "bi-gear-fill",
      alert:         "bi-exclamation-circle-fill",
    };
    return map[type] || "bi-circle-fill";
  }

  _activityColor(type) {
    const map = {
      user_login:  "kd-feed-icon-green",
      user_create: "kd-feed-icon-blue",
      data_submit: "kd-feed-icon-teal",
      alert:       "kd-feed-icon-orange",
    };
    return map[type] || "kd-feed-icon-gray";
  }

  /* ══════════════════════════════════════════════════════════════════════
     SECTION: Alerts
  ══════════════════════════════════════════════════════════════════════ */
  _renderAlerts(alerts) {
    const list = document.getElementById("kd-alerts-list");
    if (!list) return;

    if (!alerts || alerts.length === 0) {
      list.innerHTML = `<div class="kd-empty kd-empty-green"><i class="bi bi-check-circle-fill" aria-hidden="true"></i><p>لا توجد تنبيهات نشطة</p></div>`;
      return;
    }

    list.innerHTML = "";
    alerts.slice(0, 6).forEach(alert => {
      const sev = alert.severity || "info";
      const el = document.createElement("div");
      el.className = `kd-alert-item kd-alert-${sev}`;
      el.setAttribute("role", "listitem");
      el.innerHTML = `
        <span class="kd-alert-dot" aria-hidden="true"></span>
        <div class="kd-alert-body">
          <p class="kd-alert-msg">${esc(alert.message || alert.title || "")}</p>
          <time class="kd-alert-time">${fmtTimeAgo(alert.timestamp)}</time>
        </div>
        <span class="kd-alert-badge kd-sev-${sev}">${this._sevLabel(sev)}</span>
      `;
      list.appendChild(el);
    });
  }

  _sevLabel(sev) {
    const map = { critical: "حرج", warning: "تحذير", info: "معلومة", success: "ناجح" };
    return map[sev] || sev;
  }

  /* ══════════════════════════════════════════════════════════════════════
     SECTION: System Health
  ══════════════════════════════════════════════════════════════════════ */
  _renderHealth(items) {
    const grid = document.getElementById("kd-health-grid");
    if (!grid) return;
    grid.innerHTML = "";
    items.forEach(item => {
      const el = document.createElement("div");
      el.className = `kd-health-item kd-health-${item.status || "ok"}`;
      el.setAttribute("role", "listitem");
      el.innerHTML = `
        <i class="bi ${esc(item.icon || "bi-circle-fill")}" aria-hidden="true"></i>
        <span class="kd-health-label">${esc(item.label)}</span>
        <span class="kd-health-status-dot" aria-label="${item.status === "ok" ? "يعمل بشكل طبيعي" : "يحتاج انتباهاً"}"></span>
      `;
      grid.appendChild(el);
    });
  }

  /* ══════════════════════════════════════════════════════════════════════
     Counts / badges
  ══════════════════════════════════════════════════════════════════════ */
  _updateCounts(d) {
    const ac = document.getElementById("kd-activity-count");
    const al = document.getElementById("kd-alerts-count");
    if (ac) ac.textContent = d.activity.length || "0";
    if (al) {
      al.textContent = d.alerts.length || "0";
      al.className   = `kd-panel-badge ${d.alerts.length > 0 ? "kd-badge-red" : "kd-badge-green"}`;
    }
  }

  /* ══════════════════════════════════════════════════════════════════════
     UI State helpers
  ══════════════════════════════════════════════════════════════════════ */
  _showLoading() {
    this._toggle("kd-loading", true);
    this._toggle("kd-content", false);
    this._toggle("kd-error",   false);
  }

  _showContent() {
    this._toggle("kd-loading", false);
    this._toggle("kd-content", true);
    this._toggle("kd-error",   false);
  }

  _showError(msg) {
    this._toggle("kd-loading", false);
    this._toggle("kd-content", false);
    this._toggle("kd-error",   true);
    const el = document.getElementById("kd-error-msg");
    if (el) el.textContent = msg || "حدث خطأ غير متوقع.";
  }

  _toggle(id, show) {
    const el = document.getElementById(id);
    if (el) el.style.display = show ? "" : "none";
  }

  /* ── Auto-refresh ─────────────────────────────────────────────────────── */
  _startRefresh() {
    this._stopRefresh();
    this.intervalId = setInterval(() => this._load(), this.interval);
  }

  _stopRefresh() {
    if (this.intervalId) { clearInterval(this.intervalId); this.intervalId = null; }
  }
}

window.kinjoDashboard = new KinjoDashboard();
