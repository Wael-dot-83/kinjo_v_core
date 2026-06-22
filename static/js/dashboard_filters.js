/**
 * Dashboard Filters & Enhancement Layer  v1.0
 *
 * Additive module — never replaces dashboard.js. Provides:
 *   - setDateRange / showCustomDateRange / refreshDashboard
 *   - toggleKPIView (adds 'chart' option to existing cards/table switcher)
 *   - exportDashboard / filterKPIsByStatus / showAllAlerts
 *   - openKPIExplanations / quickAction
 *   - Filter bar UI injection
 *   - Chart panel (7-day attendance trend)
 *   - Smart alerts panel
 *   - Auto-refresh every 10 s via /api/dashboard/summary
 */

/* ── State ───────────────────────────────────────────────────────────────── */
window.DFE = window.DFE || {
  range: "month",
  start: null,
  end: null,
  kpiStatusFilter: null,
  autoRefreshTimer: null,
  trendChart: null,
  alertFilter: "all",
  dismissed: new Set(
    JSON.parse(localStorage.getItem("dfe_dismissed_v1") || "[]")
  ),
};

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function _dfeIsAr() {
  if (window.AppI18n && window.AppI18n.currentLang) return window.AppI18n.currentLang !== "en";
  return document.documentElement.lang !== "en";
}

function _dfeTxt(ar, en) { return _dfeIsAr() ? ar : en; }

function _dfeToIso(d) { return d.toISOString().slice(0, 10); }

function _dfeRange(range) {
  const today = new Date();
  const pad = (d) => _dfeToIso(d);
  if (range === "today") return { start: pad(today), end: pad(today) };
  if (range === "week") {
    const s = new Date(today); s.setDate(today.getDate() - 6);
    return { start: pad(s), end: pad(today) };
  }
  if (range === "quarter") {
    const s = new Date(today); s.setDate(today.getDate() - 89);
    return { start: pad(s), end: pad(today) };
  }
  // month (default)
  const s = new Date(today.getFullYear(), today.getMonth(), 1);
  return { start: pad(s), end: pad(today) };
}

function _dfeRangeLabel(range) {
  const map = {
    today: _dfeTxt("اليوم", "Today"),
    week:  _dfeTxt("هذا الأسبوع", "This Week"),
    month: _dfeTxt("هذا الشهر", "This Month"),
    quarter: _dfeTxt("هذا الربع", "This Quarter"),
    custom: _dfeTxt("مخصص", "Custom"),
  };
  return map[range] || map.month;
}

/* ── Core missing functions (called from dashboard HTML) ─────────────────── */

function setDateRange(range) {
  const dates = _dfeRange(range);
  window.DFE.range = range;
  window.DFE.start = dates.start;
  window.DFE.end = dates.end;

  // sync with existing dashboardDateRange used by dashboard.js
  window.dashboardDateRange = { range, start: dates.start, end: dates.end };

  // update dropdown button label
  const btn = document.getElementById("dateRangeBtn");
  if (btn) {
    const span = btn.querySelector("span") || btn;
    span.textContent = _dfeRangeLabel(range);
  }

  // mark active in dropdown
  document.querySelectorAll(".dropdown-menu .dropdown-item").forEach((el) => {
    const onclick = el.getAttribute("onclick") || "";
    el.classList.toggle("active", onclick.includes(`'${range}'`));
  });

  // update filter bar period pills
  document.querySelectorAll(".dfe-period-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.range === range);
  });

  // hide custom date row if not custom
  const customRow = document.getElementById("dfe-custom-row");
  if (customRow) customRow.style.display = range === "custom" ? "flex" : "none";

  updateDashboard();
  if (typeof window.loadDashboard === "function") window.loadDashboard();
}

function showCustomDateRange() {
  // Show the filter-bar custom row (our enhanced version)
  const customRow = document.getElementById("dfe-custom-row");
  if (customRow) {
    customRow.style.display = "flex";
    customRow.querySelector('input[type="date"]')?.focus();
    return;
  }
  // Fall back to Swal dialog if filter bar not rendered (small screen / PARENT role)
  if (typeof Swal !== "undefined") {
    const html = `<div class="p-3 text-start">
      <div class="mb-3"><label class="form-label">${_dfeTxt("من تاريخ", "From date")}</label>
        <input type="date" class="form-control" id="customDateFrom"></div>
      <div class="mb-3"><label class="form-label">${_dfeTxt("إلى تاريخ", "To date")}</label>
        <input type="date" class="form-control" id="customDateTo"></div>
    </div>`;
    Swal.fire({
      title: _dfeTxt("تاريخ مخصص", "Custom date range"),
      html,
      showCancelButton: true,
      confirmButtonText: _dfeTxt("تطبيق", "Apply"),
      cancelButtonText: _dfeTxt("إلغاء", "Cancel"),
      preConfirm: () => {
        const from = document.getElementById("customDateFrom")?.value;
        const to = document.getElementById("customDateTo")?.value;
        if (!from || !to) { Swal.showValidationMessage(_dfeTxt("حدد تواريخ البداية والنهاية", "Select start and end dates")); return false; }
        if (new Date(from) > new Date(to)) { Swal.showValidationMessage(_dfeTxt("البداية قبل النهاية", "Start must be before end")); return false; }
        return { from, to };
      },
    }).then((r) => {
      if (!r.isConfirmed || !r.value) return;
      window.DFE.range = "custom";
      window.DFE.start = r.value.from;
      window.DFE.end = r.value.to;
      window.dashboardDateRange = { range: "custom", start: r.value.from, end: r.value.to };
      updateDashboard();
      if (typeof window.loadDashboard === "function") window.loadDashboard();
    });
  }
}

function toggleKPIView(view) {
  const cardsView = document.getElementById("kpiCardsView");
  const tableView = document.getElementById("kpiTableView");
  const chartPanel = document.getElementById("dfe-chart-panel");
  const viewCardsBtn = document.getElementById("viewCardsBtn");
  const viewTableBtn = document.getElementById("viewTableBtn");
  const viewChartBtn = document.getElementById("dfe-view-chart-btn");

  // cards
  if (cardsView) cardsView.style.display = view === "cards" ? "" : "none";
  if (tableView) tableView.style.display = view === "table" ? "" : "none";
  if (chartPanel) chartPanel.classList.toggle("dfe-visible", view === "chart");

  // active states
  [viewCardsBtn, viewTableBtn, viewChartBtn].forEach((btn) => {
    if (btn) {
      btn.classList.remove("active");
      if (
        (btn === viewCardsBtn && view === "cards") ||
        (btn === viewTableBtn && view === "table") ||
        (btn === viewChartBtn && view === "chart")
      ) {
        btn.classList.add("active");
      }
    }
  });

  if (view === "chart") _dfeEnsureChart();
}

function refreshDashboard(event) {
  const btn = event?.currentTarget || event?.target;
  if (btn) {
    btn.classList.add("spinning");
    btn.disabled = true;
    setTimeout(() => { btn.classList.remove("spinning"); btn.disabled = false; }, 1200);
  }
  updateDashboard();
  if (typeof window.loadDashboard === "function") window.loadDashboard();
  if (typeof window.loadDecisionSupport === "function") window.loadDecisionSupport();
}

function exportDashboard() {
  const rows = [["KinJo Dashboard Export", new Date().toLocaleString()]];
  rows.push([_dfeTxt("المؤشر", "Indicator"), _dfeTxt("القيمة", "Value")]);

  const summary = window._dfeSummary || {};
  rows.push([_dfeTxt("الأطفال المسجلون", "Enrolled Children"), summary.children ?? "--"]);
  rows.push([_dfeTxt("نسبة الحضور", "Attendance Rate"), summary.attendance != null ? summary.attendance + "%" : "--"]);
  rows.push([_dfeTxt("التنبيهات", "Alerts"), summary.alerts ?? "--"]);

  const csv = rows.map((r) => r.map((c) => `"${c}"`).join(",")).join("\n");
  const link = document.createElement("a");
  link.href = "data:text/csv;charset=utf-8," + encodeURIComponent(csv);
  link.download = `kinjo_dashboard_${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
}

function filterKPIsByStatus(status) {
  window.DFE.kpiStatusFilter = window.DFE.kpiStatusFilter === status ? null : status;
  document.querySelectorAll(".kpi-status-item").forEach((item) => {
    item.classList.toggle("active-filter", item.classList.contains(`status-${status === "green" ? "green" : status === "amber" ? "amber" : "red"}`) && window.DFE.kpiStatusFilter === status);
  });
  // filter KPI cards by data-status attribute
  document.querySelectorAll("[data-kpi-status]").forEach((card) => {
    if (!window.DFE.kpiStatusFilter) {
      card.closest("[class*='col']")?.style.removeProperty("display");
    } else {
      const match = card.dataset.kpiStatus === window.DFE.kpiStatusFilter;
      const col = card.closest("[class*='col']");
      if (col) col.style.display = match ? "" : "none";
    }
  });
}

function showAllAlerts() {
  // alertsSection is now always visible at top of page
  const zone = document.getElementById("kinjoAlertZone");
  if (zone) zone.scrollIntoView({ behavior: "smooth", block: "start" });
  const panel = document.getElementById("dfe-alerts-panel");
  if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openKPIExplanations() {
  const modal = document.getElementById("kpiExplanationsModal");
  if (modal && window.bootstrap) {
    new bootstrap.Modal(modal).show();
  }
}

function quickAction(action) {
  const map = {
    reviewEnrollments: "/enrollments",
    checkAttendance: "/attendance/history",
  };
  if (map[action]) window.location.href = map[action];
}

/* ── API call ────────────────────────────────────────────────────────────── */

async function updateDashboard() {
  const { range, start, end } = window.DFE;
  try {
    const token = _dfeGetToken();
    const headers = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch("/api/dashboard/summary", {
      method: "POST",
      headers,
      body: JSON.stringify({ range, period_start: start, period_end: end }),
    });
    if (!res.ok) return;
    const data = await res.json();
    window._dfeSummary = data;
    _dfeUpdateMiniStats(data);
    _dfeUpdateChart(data.chart || []);
    _dfePulseKpiCards();
  } catch (_) {
    // silent: existing dashboard still works
  }
}

function _dfeGetToken() {
  try {
    return localStorage.getItem("kinjo_access_token") || sessionStorage.getItem("kinjo_access_token") || null;
  } catch (_) { return null; }
}

/* ── Filter bar ──────────────────────────────────────────────────────────── */

function _dfeInjectFilterBar() {
  const el = document.getElementById("dfe-filter-bar");
  if (!el) return;

  const isAr = _dfeIsAr();
  const today = _dfeToIso(new Date());
  const monthStart = _dfeToIso(new Date(new Date().getFullYear(), new Date().getMonth(), 1));

  el.innerHTML = `
    <div class="dfe-period-group" role="group" aria-label="${_dfeTxt("نطاق التاريخ", "Date range")}">
      <button class="dfe-period-btn" data-range="today" onclick="setDateRange('today')">${_dfeTxt("اليوم", "Today")}</button>
      <button class="dfe-period-btn" data-range="week" onclick="setDateRange('week')">${_dfeTxt("أسبوع", "Week")}</button>
      <button class="dfe-period-btn active" data-range="month" onclick="setDateRange('month')">${_dfeTxt("الشهر", "Month")}</button>
      <button class="dfe-period-btn" data-range="quarter" onclick="setDateRange('quarter')">${_dfeTxt("ربع سنوي", "Quarter")}</button>
    </div>

    <div class="dfe-date-range" id="dfe-custom-row" style="display:none">
      <input type="date" class="dfe-date-input" id="dfe-start-date" value="${monthStart}"
             aria-label="${_dfeTxt("تاريخ البداية", "Start date")}">
      <span class="dfe-date-sep">→</span>
      <input type="date" class="dfe-date-input" id="dfe-end-date" value="${today}"
             aria-label="${_dfeTxt("تاريخ النهاية", "End date")}">
      <button class="dfe-period-btn" onclick="_dfeApplyCustomRange()">${_dfeTxt("تطبيق", "Apply")}</button>
    </div>

    <div class="dfe-bar-end">
      <div id="dfe-mini-children" style="display:none;font-size:.8rem;font-weight:700;color:#1a2233;">
        <i class="bi bi-people-fill me-1 text-primary"></i><span id="dfe-val-children">--</span>
      </div>
      <div id="dfe-mini-att" style="display:none;font-size:.8rem;font-weight:700;color:#198754;">
        <i class="bi bi-calendar-check-fill me-1"></i><span id="dfe-val-att">--</span>%
      </div>
      <div class="dfe-live-badge" aria-label="${_dfeTxt("تحديث تلقائي", "Auto-refresh")}">
        <span class="dfe-live-dot"></span>
        ${_dfeTxt("مباشر", "LIVE")}
      </div>
      <button class="dfe-refresh-btn" onclick="refreshDashboard(event)"
              title="${_dfeTxt("تحديث", "Refresh")}" aria-label="${_dfeTxt("تحديث لوحة التحكم", "Refresh dashboard")}">
        <i class="bi bi-arrow-clockwise"></i>
      </button>
    </div>
  `;

  // Wire up custom range inputs to trigger on Enter
  setTimeout(() => {
    const start = document.getElementById("dfe-start-date");
    const end = document.getElementById("dfe-end-date");
    if (start) start.addEventListener("change", () => { if (end?.value) _dfeApplyCustomRange(); });
    if (end) end.addEventListener("change", () => { if (start?.value) _dfeApplyCustomRange(); });
  }, 0);
}

function _dfeApplyCustomRange() {
  const start = document.getElementById("dfe-start-date")?.value;
  const end = document.getElementById("dfe-end-date")?.value;
  if (!start || !end) return;

  window.DFE.range = "custom";
  window.DFE.start = start;
  window.DFE.end = end;
  window.dashboardDateRange = { range: "custom", start, end };

  document.querySelectorAll(".dfe-period-btn").forEach((b) => b.classList.remove("active"));

  updateDashboard();
  if (typeof window.loadDashboard === "function") window.loadDashboard();
}

function _dfeUpdateMiniStats(data) {
  const childEl = document.getElementById("dfe-val-children");
  const attEl = document.getElementById("dfe-val-att");
  const miniChildren = document.getElementById("dfe-mini-children");
  const miniAtt = document.getElementById("dfe-mini-att");

  if (childEl && data.children != null) {
    childEl.textContent = Number(data.children).toLocaleString();
    if (miniChildren) miniChildren.style.display = "";
  }
  if (attEl && data.attendance != null) {
    attEl.textContent = data.attendance;
    if (miniAtt) miniAtt.style.display = "";
  }

  // also update chart mini stats
  _dfeSetMiniStat("dfe-chart-children", data.children);
  _dfeSetMiniStat("dfe-chart-att", data.attendance != null ? data.attendance + "%" : null);
  _dfeSetMiniStat("dfe-chart-alerts", data.alerts);
}

function _dfeSetMiniStat(id, val) {
  const el = document.getElementById(id);
  if (el && val != null) el.textContent = val;
}

/* ── Chart panel ─────────────────────────────────────────────────────────── */

function _dfeInjectChartPanel() {
  // Find existing KPI card (Admin/Manager block) and inject chart panel after it
  const kpiCard = document.querySelector("[id='kpiCardsView']")?.closest(".card");
  const container = kpiCard?.closest(".col-12") || kpiCard?.closest(".row")?.closest(".row");

  // Also look for the btn-group with viewCardsBtn / viewTableBtn and add chart button
  const viewCardsBtn = document.getElementById("viewCardsBtn");
  if (viewCardsBtn) {
    const btnGroup = viewCardsBtn.closest(".btn-group");
    if (btnGroup && !document.getElementById("dfe-view-chart-btn")) {
      const chartBtn = document.createElement("button");
      chartBtn.type = "button";
      chartBtn.id = "dfe-view-chart-btn";
      chartBtn.className = "btn btn-outline-primary";
      chartBtn.title = _dfeTxt("عرض الرسم البياني", "Chart view");
      chartBtn.setAttribute("aria-label", _dfeTxt("عرض الرسم البياني", "Chart view"));
      chartBtn.innerHTML = '<i class="bi bi-graph-up-arrow"></i>';
      chartBtn.addEventListener("click", () => toggleKPIView("chart"));
      btnGroup.appendChild(chartBtn);
    }
  }

  // Inject chart panel div
  let panel = document.getElementById("dfe-chart-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "dfe-chart-panel";

    // Try to insert after the KPI cards block
    const afterTarget = document.getElementById("kpiTableView")?.closest(".card");
    if (afterTarget && afterTarget.parentNode) {
      afterTarget.parentNode.insertBefore(panel, afterTarget.nextSibling);
    } else {
      // Fallback: append to main content
      document.querySelector(".container-fluid")?.appendChild(panel);
    }
  }

  panel.innerHTML = `
    <div class="dfe-chart-card mt-3">
      <div class="dfe-chart-header">
        <div class="dfe-chart-title">
          <i class="bi bi-graph-up-arrow me-2 text-primary"></i>
          ${_dfeTxt("اتجاه الحضور (7 أيام)", "Attendance Trend (7 Days)")}
        </div>
        <div class="dfe-chart-type-btns">
          <button class="dfe-chart-type-btn active" data-chart-type="line" onclick="_dfeSwitchChartType('line')">
            ${_dfeTxt("خطي", "Line")}
          </button>
          <button class="dfe-chart-type-btn" data-chart-type="bar" onclick="_dfeSwitchChartType('bar')">
            ${_dfeTxt("أعمدة", "Bar")}
          </button>
          <button class="dfe-chart-type-btn" data-chart-type="area" onclick="_dfeSwitchChartType('area')">
            ${_dfeTxt("مساحة", "Area")}
          </button>
        </div>
      </div>
      <div class="dfe-chart-body">
        <canvas id="dfe-trend-canvas"></canvas>
        <div class="dfe-chart-loading" id="dfe-chart-loading">
          <div class="spinner-border spinner-border-sm text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
          </div>
        </div>
      </div>
      <div class="dfe-mini-stats">
        <div class="dfe-mini-stat">
          <div class="dfe-mini-stat-val text-primary" id="dfe-chart-children">--</div>
          <div class="dfe-mini-stat-lbl">${_dfeTxt("أطفال مسجلون", "Enrolled Children")}</div>
        </div>
        <div class="dfe-mini-stat">
          <div class="dfe-mini-stat-val text-success" id="dfe-chart-att">--</div>
          <div class="dfe-mini-stat-lbl">${_dfeTxt("نسبة الحضور", "Attendance Rate")}</div>
        </div>
        <div class="dfe-mini-stat">
          <div class="dfe-mini-stat-val text-danger" id="dfe-chart-alerts">--</div>
          <div class="dfe-mini-stat-lbl">${_dfeTxt("تنبيهات", "Alerts")}</div>
        </div>
      </div>
    </div>
  `;
}

function _dfeSwitchChartType(type) {
  document.querySelectorAll(".dfe-chart-type-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.chartType === type);
  });
  window.DFE._chartType = type;
  _dfeEnsureChart();
}

function _dfeDayLabels() {
  const labels = [];
  const isAr = _dfeIsAr();
  const days = isAr
    ? ["أحد", "إث", "ثل", "أر", "خم", "جم", "سب"]
    : ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(); d.setDate(d.getDate() - i);
    labels.push(days[d.getDay()]);
  }
  return labels;
}

function _dfeEnsureChart() {
  if (!window.Chart) return; // Chart.js not loaded yet
  const canvas = document.getElementById("dfe-trend-canvas");
  if (!canvas) return;

  const data = window._dfeSummary?.chart || [0, 0, 0, 0, 0, 0, 0];
  const type = window.DFE._chartType || "line";

  if (window.DFE.trendChart) {
    window.DFE.trendChart.destroy();
    window.DFE.trendChart = null;
  }

  const isArea = type === "area";
  const chartType = isArea ? "line" : type;
  const color = getComputedStyle(document.documentElement).getPropertyValue("--bs-primary").trim() || "#0d6efd";

  window.DFE.trendChart = new Chart(canvas, {
    type: chartType,
    data: {
      labels: _dfeDayLabels(),
      datasets: [{
        label: _dfeTxt("نسبة الحضور %", "Attendance %"),
        data,
        borderColor: color || "#0d6efd",
        backgroundColor: isArea ? (color ? `${color}22` : "rgba(13,110,253,.12)") : (chartType === "bar" ? "rgba(13,110,253,.7)" : "transparent"),
        fill: isArea,
        tension: 0.4,
        pointRadius: 4,
        pointHoverRadius: 6,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: { label: (ctx) => ` ${ctx.parsed.y}%` },
        },
      },
      scales: {
        y: { min: 0, max: 100, ticks: { callback: (v) => v + "%" } },
        x: { grid: { display: false } },
      },
    },
  });
}

function _dfeUpdateChart(trend) {
  if (!window.DFE.trendChart) {
    _dfeEnsureChart();
    return;
  }
  window.DFE.trendChart.data.datasets[0].data = trend;
  window.DFE.trendChart.update("active");
}

/* ── Alerts panel ────────────────────────────────────────────────────────── */

function _dfeInjectAlertsPanel() {
  let panel = document.getElementById("dfe-alerts-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "dfe-alerts-panel";
    // Append at the very end of main content container
    const container = document.querySelector(".container-fluid.px-0") || document.querySelector(".container-fluid");
    if (container) container.appendChild(panel);
  }

  // Seed with structural + live alerts from existing alertsContainer if present
  const existing = document.getElementById("alertsContainer");
  const existingHtml = existing ? existing.innerHTML.trim() : "";

  panel.innerHTML = `
    <div class="dfe-alert-header">
      <div class="dfe-alert-title">
        <span style="display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:8px;background:rgba(220,53,69,.1);color:#dc3545;">
          <i class="bi bi-bell-fill"></i>
        </span>
        ${_dfeTxt("التنبيهات الذكية", "Smart Alerts")}
        <span class="badge bg-danger rounded-pill ms-1" id="dfe-alert-badge" style="display:none"></span>
      </div>
      <div class="dfe-alert-filters">
        <button class="dfe-alert-filter active" data-sev="all" onclick="_dfeAlertFilter('all')">${_dfeTxt("الكل", "All")}</button>
        <button class="dfe-alert-filter" data-sev="high" onclick="_dfeAlertFilter('high')">${_dfeTxt("حرج", "Critical")}</button>
        <button class="dfe-alert-filter" data-sev="medium" onclick="_dfeAlertFilter('medium')">${_dfeTxt("تحذير", "Warning")}</button>
      </div>
    </div>
    <div class="dfe-alert-list" id="dfe-alert-list">
      <div id="dfe-alert-empty" class="text-center py-4 text-muted" style="display:none">
        <i class="bi bi-check-circle fs-2 d-block mb-2 opacity-25"></i>
        <small>${_dfeTxt("لا توجد تنبيهات نشطة", "No active alerts")}</small>
      </div>
    </div>
  `;

  _dfeBuildAlerts();
}

const DFE_ALERT_TEMPLATES = () => [
  {
    id: "pending_enr",
    sev: "medium",
    icon: "bi-person-plus-fill",
    color: "#f59e0b",
    title: _dfeTxt("طلبات تسجيل معلقة", "Pending Enrollment Requests"),
    desc: _dfeTxt("تحتاج إلى مراجعة طلبات التسجيل المعلقة.", "Pending enrollment requests need review."),
    href: "/enrollments",
  },
  {
    id: "low_att",
    sev: "high",
    icon: "bi-exclamation-triangle-fill",
    color: "#ef4444",
    title: _dfeTxt("انخفاض في الحضور", "Low Attendance Detected"),
    desc: _dfeTxt("نسبة الحضور أقل من المعيار هذا الأسبوع.", "Attendance rate below standard this week."),
    href: "/attendance",
  },
  {
    id: "incidents",
    sev: "high",
    icon: "bi-shield-exclamation",
    color: "#ef4444",
    title: _dfeTxt("حوادث مبلغ عنها اليوم", "Incidents Reported Today"),
    desc: _dfeTxt("يوجد حوادث تتطلب المراجعة.", "There are incidents requiring review."),
    href: "/safety",
  },
];

function _dfeBuildAlerts() {
  const list = document.getElementById("dfe-alert-list");
  if (!list) return;

  const summary = window._dfeSummary || {};
  const alerts = DFE_ALERT_TEMPLATES();

  // filter based on live data
  const active = alerts.filter((a) => {
    if (a.id === "pending_enr") return (summary.alerts ?? 1) > 0;
    if (a.id === "low_att") return (summary.attendance ?? 100) < 75;
    if (a.id === "incidents") return (summary.alerts ?? 0) > 0;
    return true;
  }).filter((a) => !window.DFE.dismissed.has(a.id));

  const filtered = window.DFE.alertFilter === "all"
    ? active
    : active.filter((a) => a.sev === window.DFE.alertFilter);

  const empty = document.getElementById("dfe-alert-empty");

  // remove old items
  list.querySelectorAll(".dfe-alert-item").forEach((n) => n.remove());

  if (filtered.length === 0) {
    if (empty) empty.style.display = "";
  } else {
    if (empty) empty.style.display = "none";
    filtered.forEach((a) => {
      const item = document.createElement("div");
      item.className = "dfe-alert-item";
      item.dataset.alertId = a.id;
      item.style.setProperty("--sev-color", a.color);
      item.innerHTML = `
        <div class="dfe-alert-icon"><i class="bi ${a.icon}"></i></div>
        <div class="dfe-alert-body">
          <div class="dfe-alert-name">${a.title}</div>
          <div class="dfe-alert-desc">${a.desc}</div>
          <div class="dfe-alert-btns">
            <a class="dfe-alert-btn view" href="${a.href}">${_dfeTxt("عرض التفاصيل", "View Details")}</a>
            <button class="dfe-alert-btn dismiss" onclick="_dfeDismissAlert('${a.id}')">${_dfeTxt("تجاهل", "Dismiss")}</button>
          </div>
        </div>
      `;
      list.appendChild(item);
    });
  }

  // update badge
  const badge = document.getElementById("dfe-alert-badge");
  if (badge) {
    if (filtered.length > 0) {
      badge.textContent = filtered.length;
      badge.style.display = "";
    } else {
      badge.style.display = "none";
    }
  }

  // Also update the main alert count badges in existing dashboard
  const alertCountEl = document.getElementById("alertCount");
  if (alertCountEl && summary.alerts != null) alertCountEl.textContent = summary.alerts;
}

function _dfeAlertFilter(sev) {
  window.DFE.alertFilter = sev;
  document.querySelectorAll(".dfe-alert-filter").forEach((b) => {
    b.classList.toggle("active", b.dataset.sev === sev);
  });
  _dfeBuildAlerts();
}

function _dfeDismissAlert(id) {
  window.DFE.dismissed.add(id);
  localStorage.setItem("dfe_dismissed_v1", JSON.stringify([...window.DFE.dismissed]));
  const item = document.querySelector(`[data-alert-id="${id}"]`);
  if (item) {
    item.classList.add("dismissed");
    setTimeout(() => item.remove(), 400);
  }
  setTimeout(_dfeBuildAlerts, 450);
}

/* ── KPI card pulse ──────────────────────────────────────────────────────── */

function _dfePulseKpiCards() {
  document.querySelectorAll(".kpi-value, .kj-stat-value").forEach((el) => {
    el.classList.remove("dfe-kpi-pulse");
    void el.offsetWidth; // reflow
    el.classList.add("dfe-kpi-pulse");
    setTimeout(() => el.classList.remove("dfe-kpi-pulse"), 600);
  });
}

/* ── Chart.js loader ─────────────────────────────────────────────────────── */

function _dfeLoadChartJs(cb) {
  if (window.Chart) { cb(); return; }
  const s = document.createElement("script");
  s.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js";
  s.onload = cb;
  document.head.appendChild(s);
}

/* ── Auto-refresh ────────────────────────────────────────────────────────── */

function _dfeStartAutoRefresh() {
  if (window.DFE.autoRefreshTimer) clearInterval(window.DFE.autoRefreshTimer);
  window.DFE.autoRefreshTimer = setInterval(updateDashboard, 10000);
}

/* ── Boot ────────────────────────────────────────────────────────────────── */

document.addEventListener("DOMContentLoaded", function () {
  // Sync DFE state with existing dashboardDateRange
  if (window.dashboardDateRange) {
    window.DFE.range = window.dashboardDateRange.range || "month";
    window.DFE.start = window.dashboardDateRange.start || null;
    window.DFE.end = window.dashboardDateRange.end || null;
  }

  _dfeInjectFilterBar();
  _dfeInjectAlertsPanel();

  _dfeLoadChartJs(() => {
    _dfeInjectChartPanel();
    document.addEventListener("chartjs:ready", () => _dfeEnsureChart());
  });

  // initial data fetch
  updateDashboard();

  // start auto-refresh
  _dfeStartAutoRefresh();
});

/* expose to global scope so template onclick attrs work */
window.setDateRange = setDateRange;
window.showCustomDateRange = showCustomDateRange;
window.toggleKPIView = toggleKPIView;
window.refreshDashboard = refreshDashboard;
window.exportDashboard = exportDashboard;
window.filterKPIsByStatus = filterKPIsByStatus;
window.showAllAlerts = showAllAlerts;
window.openKPIExplanations = openKPIExplanations;
window.quickAction = quickAction;
window.updateDashboard = updateDashboard;
window._dfeApplyCustomRange = _dfeApplyCustomRange;
window._dfeAlertFilter = _dfeAlertFilter;
window._dfeDismissAlert = _dfeDismissAlert;
window._dfeSwitchChartType = _dfeSwitchChartType;
