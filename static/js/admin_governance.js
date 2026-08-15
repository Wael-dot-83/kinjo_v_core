/**
 * Admin Governance Reports — Daily Report Compliance Dashboard
 */

let funnelChart = null;
let trendChart = null;
let _reminderTarget = null;
// GET /api/admin/governance/reminders has always supported page/page_size and
// returned {total, page, page_size, items} — this page called it with a
// hardcoded page=1&page_size=10 on every refresh and never read `total`, so
// only the 10 most recent reminders were ever visible with no indication
// more existed, even though the backend already fully supports paging
// through them (same bug class as the Users page's dead pagination).
let remindersPage = 1;
const REMINDERS_PAGE_SIZE = 10;
let remindersTotal = 0;

function governanceLangCode() {
  return (
    window.AdminI18n?.getCurrentLanguage?.().code ||
    window.AppI18n?.currentLang ||
    localStorage.getItem("admin_language") ||
    localStorage.getItem("kinjo_lang") ||
    document.documentElement.lang ||
    "ar"
  );
}

function governanceText(arText, enText) {
  return String(governanceLangCode()).toLowerCase().startsWith("en") ? enText : arText;
}

function governanceLocale() {
  return governanceText("ar-JO", "en-US");
}

function governanceLiteral(value) {
  const raw = String(value ?? "");
  if (!raw) return "";
  if (typeof window.AdminI18n?.replaceLiteralSegments === "function") {
    return window.AdminI18n.replaceLiteralSegments(raw);
  }
  if (typeof window.AppI18n?.replaceLiteralSegments === "function") {
    return window.AppI18n.replaceLiteralSegments(raw);
  }
  return raw;
}

// e4f10a5 removed this page's local escapeHtml (correctly -- sanitize.js
// defines a global one) but removed showMessage along with it while leaving
// all four call sites in place, so every error path on this page threw
// "showMessage is not defined" instead of telling the admin what went wrong.
function showMessage({ icon = "info", title = "", text = "", timer = 0 } = {}) {
  if (window.Swal && typeof window.Swal.fire === "function") {
    return window.Swal.fire({
      icon,
      title,
      text,
      timer: timer || undefined,
      showConfirmButton: !timer,
    });
  }
  window.alert([title, text].filter(Boolean).join("\n"));
  return Promise.resolve();
}

function getKgName(item) {
  if (!item) return "";
  const raw = String(governanceLangCode()).toLowerCase().startsWith("en")
    ? (item.name_en || item.name_ar || `KG#${item.kindergarten_id || item.id}`)
    : (item.name_ar || item.name_en || `KG#${item.kindergarten_id || item.id}`);
  return escapeHtml(governanceLiteral(raw));
}

function formatReminderType(reminderType) {
  const labels = {
    low_submission_rate: governanceText("انخفاض نسبة التقديم", "Low submission rate"),
  };
  return labels[reminderType] || reminderType || "--";
}

async function governanceFetch(url, options = {}) {
  const response = await fetchWithAuth(url, options);
  if (!response) {
    throw new Error("Unauthenticated");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw { status: response.status, body };
  }
  return response.json();
}

function getDateRange() {
  const end = document.getElementById("endDate").value;
  const start = document.getElementById("startDate").value;
  return { start, end };
}

function formatPercent(val) {
  if (val == null || val === 0) return "0%";
  return (val * 100).toFixed(1) + "%";
}

function formatPct(val) {
  if (val == null) return "--";
  return Number(val).toFixed(1) + "%";
}

function formatHours(h) {
  if (h == null) return "--";
  if (h < 1) {
    return governanceText(`${Math.round(h * 60)} د`, `${Math.round(h * 60)} m`);
  }
  return governanceText(`${h.toFixed(1)} س`, `${h.toFixed(1)} h`);
}

// ─── Load all governance data ────────────────────────────────────────────

async function loadGovernanceData() {
  const { start, end } = getDateRange();
  if (!start || !end) return;
  const refreshBtn = document.getElementById("refreshBtn");
  const originalRefreshHtml = refreshBtn ? refreshBtn.innerHTML : "";

  try {
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${governanceText("جارٍ تحميل البيانات، يرجى الانتظار.", "Loading...")}`;
    }
    const query = new URLSearchParams({ start_date: start, end_date: end }).toString();

    remindersPage = 1;
    const [kpis, board, reminders, trend, safeguarding] = await Promise.all([
      governanceFetch(`/api/admin/governance/kpis?${query}`),
      governanceFetch(`/api/admin/governance/leaderboard?${query}`),
      governanceFetch(`/api/admin/governance/reminders?page=${remindersPage}&page_size=${REMINDERS_PAGE_SIZE}`),
      governanceFetch(`/api/admin/governance/trend?days=30`),
      governanceFetch(`/api/admin/governance/safeguarding`),
    ]);

    renderKPICards(kpis);
    renderGQI(kpis);
    renderFunnelChart(kpis.funnel);
    renderTimeliness(kpis.timeliness, kpis.consistency);
    renderTrendChart(trend.trend || []);
    renderSafeguarding(safeguarding);
    renderLeaderboard(board.leaderboard);
    renderLowPerformers(board.low_performers);
    remindersTotal = reminders.total || 0;
    renderReminders(reminders.items);
    renderRemindersPagination();
  } catch (err) {
    console.error("Failed to load governance data", err);
    // fetchWithAuth throws a plain Error carrying the backend's own detail in
    // .message, so reading only err.body.detail hid every real cause behind
    // the generic string below.
    const detail = err?.body?.detail;
    const message =
      (typeof detail === "string" && detail) ||
      detail?.message ||
      err?.message ||
      governanceText(
        "تعذر تحميل بيانات الحوكمة. حاول مرة أخرى.",
        "Unable to load governance data. Please try again."
      );
    showMessage({
      icon: "error",
      title: governanceText("خطأ في التحميل", "Loading error"),
      text: message,
    });
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.innerHTML = originalRefreshHtml;
    }
  }
}

// ─── KPI Cards ───────────────────────────────────────────────────────────

function renderKPICards(kpis) {
  const agg = kpis.funnel?.aggregate || {};
  document.getElementById("kpiSubmissionRate").textContent = formatPercent(agg.submission_rate);
  document.getElementById("kpiSubmitted").textContent = agg.submitted || 0;
  document.getElementById("kpiRequired").textContent = agg.required || 0;
  document.getElementById("kpiDeliveryRate").textContent = formatPercent(agg.delivery_rate);
  document.getElementById("kpiDelivered").textContent = agg.delivered || 0;
  document.getElementById("kpiViewRate").textContent = formatPercent(agg.view_rate);
  document.getElementById("kpiViewed").textContent = agg.viewed || 0;

  const qualityKgs = kpis.quality?.per_kindergarten || {};
  const allQuality = Object.values(qualityKgs);
  if (allQuality.length > 0) {
    const totalApproved = allQuality.reduce((s, q) => s + (q.approved || 0), 0);
    const totalAll = allQuality.reduce((s, q) => s + (q.total || 0), 0);
    const rate = totalAll ? totalApproved / totalAll : 0;
    const totalRejected = allQuality.reduce((s, q) => s + (q.rejected || 0), 0);
    document.getElementById("kpiQualityRate").textContent = formatPercent(rate);
    document.getElementById("kpiRejectionInfo").textContent = governanceText(
      `${totalRejected} مرفوض من ${totalAll}`,
      `${totalRejected} rejected out of ${totalAll}`
    );
  }
}

// ─── GQI Sub-indicators ──────────────────────────────────────────────────

function renderGQI(kpis) {
  const gqi = kpis.gqi || {};
  const sub = gqi.sub_indicators || {};
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  const rawScore = gqi.gqi != null ? clamp(gqi.gqi, 0, 100) : null;
  const scoreEl = document.getElementById("gqiScore");
  if (scoreEl) {
    scoreEl.textContent = rawScore != null ? `${rawScore.toFixed(1)} / 100` : "--";
    scoreEl.className = "badge ms-2 fs-6 " + (
      rawScore == null ? "bg-secondary" :
      rawScore >= 80 ? "bg-success" :
      rawScore >= 60 ? "bg-warning text-dark" :
      "bg-danger"
    );
  }

  const setGqi = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val != null ? `${clamp(Number(val), 0, 100).toFixed(1)}%` : "--";
  };
  setGqi("gqiReportSubmission", sub.report_submission);
  setGqi("gqiRatioCompliance", sub.ratio_compliance);
  setGqi("gqiLicenseValidity", sub.license_validity);
  setGqi("gqiTrainingCoverage", sub.training_coverage);
  setGqi("gqiIncidentSla", sub.incident_sla);

  const rejEl = document.getElementById("kpiRejectionRate");
  if (rejEl) {
    rejEl.textContent = kpis.rejection_rate != null ? `${Number(kpis.rejection_rate).toFixed(1)}%` : "--";
  }
  const morEl = document.getElementById("kpiMorningRate");
  if (morEl) {
    morEl.textContent = kpis.morning_rate != null ? `${Number(kpis.morning_rate).toFixed(1)}%` : "--";
  }
}

// ─── Funnel Chart ────────────────────────────────────────────────────────

function renderFunnelChart(funnel) {
  const agg = funnel?.aggregate || {};
  const ctx = document.getElementById("funnelChart").getContext("2d");

  if (funnelChart) funnelChart.destroy();

  funnelChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: [
        governanceText("المطلوب", "Required"),
        governanceText("المقدم", "Submitted"),
        governanceText("المسلم", "Delivered"),
        governanceText("المشاهد", "Viewed"),
      ],
      datasets: [
        {
          data: [agg.required || 0, agg.submitted || 0, agg.delivered || 0, agg.viewed || 0],
          backgroundColor: ["#6c757d", "#4F46E5", "#198754", "#B49B3B"],
          borderRadius: 6,
        },
      ],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, grid: { display: false } },
        y: { grid: { display: false } },
      },
    },
  });
}

// ─── Timeliness & Consistency ────────────────────────────────────────────

function renderTimeliness(timeliness, consistency) {
  const tKgs = Object.values(timeliness?.per_kindergarten || {});
  if (tKgs.length > 0) {
    const medians = tKgs.map((t) => t.median_hours).filter((v) => v != null);
    const p90s = tKgs.map((t) => t.p90_hours).filter((v) => v != null);
    const avgMedian = medians.length ? medians.reduce((a, b) => a + b, 0) / medians.length : null;
    const avgP90 = p90s.length ? p90s.reduce((a, b) => a + b, 0) / p90s.length : null;
    document.getElementById("medianTimeliness").textContent = formatHours(avgMedian);
    document.getElementById("p90Timeliness").textContent = formatHours(avgP90);
  }

  const cKgs = Object.values(consistency?.per_kindergarten || {});
  if (cKgs.length > 0) {
    const avg = cKgs.reduce((s, c) => s + (c.consistency_index || 0), 0) / cKgs.length;
    document.getElementById("avgConsistency").textContent = formatPercent(avg);
  }
}

// ─── 30-Day Trend Chart ──────────────────────────────────────────────────

function renderTrendChart(trend) {
  const ctx = document.getElementById("trendChart");
  if (!ctx) return;

  if (trendChart) trendChart.destroy();

  const labels = trend.map((p) => {
    const d = new Date(p.date);
    return d.toLocaleDateString(governanceLocale(), { month: "short", day: "numeric" });
  });
  const rates = trend.map((p) => +(p.submission_rate * 100).toFixed(1));

  trendChart = new Chart(ctx.getContext("2d"), {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: governanceText("نسبة التقديم %", "Submission Rate %"),
          data: rates,
          borderColor: "#4F46E5",
          backgroundColor: "rgba(79,70,229,0.08)",
          fill: true,
          tension: 0.35,
          pointRadius: 2,
          borderWidth: 2,
        },
        {
          label: governanceText("هدف 80%", "Target 80%"),
          data: trend.map(() => 80),
          borderColor: "#198754",
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend: { position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%`,
          },
        },
      },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { callback: (v) => v + "%" } },
        x: { grid: { display: false } },
      },
    },
  });
}

// ─── Safeguarding Overlap ────────────────────────────────────────────────

function renderSafeguarding(data) {
  const section = document.getElementById("safeguardingSection");
  const list = document.getElementById("safeguardingList");
  const countEl = document.getElementById("safeguardingCount");
  if (!section || !list) return;

  const items = data?.overlapping || [];
  if (items.length === 0) {
    section.classList.add("d-none");
    return;
  }

  section.classList.remove("d-none");
  if (countEl) countEl.textContent = items.length;

  list.innerHTML = items
    .map((item) => {
      const name = escapeHtml(
        governanceLangCode().startsWith("en")
          ? (item.name_en || item.name_ar || `KG#${item.kindergarten_id}`)
          : (item.name_ar || item.name_en || `KG#${item.kindergarten_id}`)
      );
      const subRate = (+(item.submission_rate || 0) * 100).toFixed(1);
      return `
        <div class="col-md-4">
          <div class="border border-danger rounded p-3 bg-danger bg-opacity-5">
            <div class="fw-bold text-danger">${name}</div>
            <div class="small text-on-surface-variant mt-1">
              <i class="bi bi-graph-down-arrow me-1"></i>
              ${governanceText("نسبة التقديم:", "Submission:")} ${subRate}%
            </div>
            <div class="small text-on-surface-variant">
              <i class="bi bi-exclamation-triangle me-1"></i>
              ${item.open_incidents} ${governanceText("حادثة مفتوحة", "open incident(s)")}
            </div>
          </div>
        </div>`;
    })
    .join("");
}

// ─── Leaderboard ─────────────────────────────────────────────────────────

function filterPrioritizedTable() {
  const input = document.getElementById("searchPrioritized");
  if (!input) return;
  const filter = input.value.toLowerCase();
  const rows = document.querySelectorAll("#leaderboardBody tr");
  rows.forEach((row) => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(filter) ? "" : "none";
  });
}

function renderLeaderboard(entries) {
  const tbody = document.getElementById("leaderboardBody");
  const countEl = document.getElementById("prioritizedCount");
  if (!entries || entries.length === 0) {
    if (countEl) countEl.textContent = "0";
    tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted py-4">${governanceText("لا توجد بيانات كافية للحضانات ذات الأولوية", "No prioritized nursery data available")}</td></tr>`;
    return;
  }

  if (countEl) countEl.textContent = entries.length;

  tbody.innerHTML = entries
    .map((e) => {
      const rankClass = e.rank <= 3 ? `badge bg-warning text-dark fs-6 px-2 py-1` : "badge bg-light text-dark border px-2 py-1";
      const kgName = getKgName(e);
      const govBadge = e.governorate ? `<span class="badge bg-secondary-subtle text-secondary ms-1 small">${escapeHtml(e.governorate)}</span>` : "";
      
      const bayesianScore = e.bayesian_score != null ? (e.bayesian_score * 100).toFixed(1) : 0;
      let scoreBadgeClass = "bg-danger-subtle text-danger";
      let statusBadge = governanceText("ضعيف / يحتاج متابعة", "Needs Attention");
      let statusClass = "bg-danger-subtle text-danger";

      if (bayesianScore >= 80) {
        scoreBadgeClass = "bg-success-subtle text-success border border-success-subtle";
        statusBadge = governanceText("ممتاز / ممتثل", "Excellent / Compliant");
        statusClass = "bg-success-subtle text-success border border-success-subtle";
      } else if (bayesianScore >= 60) {
        scoreBadgeClass = "bg-warning-subtle text-warning-emphasis border border-warning-subtle";
        statusBadge = governanceText("مستقر / جيد", "Stable / Good");
        statusClass = "bg-warning-subtle text-warning-emphasis border border-warning-subtle";
      }

      const rawRate = (+(e.raw_rate || 0) * 100).toFixed(1);
      const rejRate = e.rejection_rate != null ? `${Number(e.rejection_rate).toFixed(1)}%` : "--";
      const ciVal = e.consistency_index != null ? `${Number(e.consistency_index).toFixed(1)}%` : "--";
      const lastDate = e.last_report_date
        ? new Date(e.last_report_date).toLocaleDateString(governanceLocale())
        : "--";

      return `<tr>
          <td class="text-center"><span class="${rankClass}">${e.rank}</span></td>
          <td><div class="fw-bold text-dark">${kgName}</div>${govBadge}</td>
          <td class="text-center fw-semibold">${e.required || 0}</td>
          <td class="text-center text-primary fw-semibold">${e.submitted || 0}</td>
          <td class="text-center">
            <div class="d-flex align-items-center justify-content-center gap-1">
              <span class="fw-bold">${rawRate}%</span>
            </div>
          </td>
          <td class="text-center">
            <span class="badge ${scoreBadgeClass} fs-6 px-2 py-1">${bayesianScore}%</span>
          </td>
          <td class="text-center"><span class="${e.rejection_rate > 15 ? 'text-danger fw-bold' : 'text-muted'}">${rejRate}</span></td>
          <td class="text-center fw-semibold text-secondary">${ciVal}</td>
          <td class="text-center small text-muted">${lastDate}</td>
          <td class="text-center"><span class="badge ${statusClass} px-2 py-1">${statusBadge}</span></td>
          <td class="text-end pe-3">
              <button class="btn btn-sm btn-outline-warning js-reminder-btn"
                      data-target-type="kindergarten"
                      data-target-id="${e.kindergarten_id}"
                      data-target-name="${kgName}"
                      title="${governanceText('إرسال تذكير حوكمة إلى', 'Send governance reminder to')} ${kgName}">
                  <i class="bi bi-bell-fill me-1" aria-hidden="true"></i>${governanceText('تذكير', 'Remind')}
              </button>
          </td>
      </tr>`;
    })
    .join("");
}

// ─── Nurseries Requiring Improvement ─────────────────────────────────────

function renderLowPerformers(items) {
  const tbody = document.getElementById("lowPerformersTableBody");
  const countEl = document.getElementById("improvementCount");
  if (!items || items.length === 0) {
    if (countEl) countEl.textContent = "0";
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">${governanceText("لا توجد حضانات تتطلب تدخلاً عاجلاً حالياً", "No nurseries requiring immediate intervention at this time")}</td></tr>`;
    }
    return;
  }

  if (countEl) countEl.textContent = items.length;

  if (tbody) {
    tbody.innerHTML = items
      .map((lp) => {
        const kgName = getKgName(lp);
        const govBadge = lp.governorate ? `<span class="badge bg-secondary-subtle text-secondary ms-1 small">${escapeHtml(lp.governorate)}</span>` : "";
        const subRate = (+(lp.submission_rate || 0) * 100).toFixed(1);
        const openIncidents = lp.open_incidents || 0;
        const safeguardingBadge = openIncidents > 0
          ? `<span class="badge bg-danger text-white"><i class="bi bi-shield-exclamation me-1"></i>${openIncidents} ${governanceText("حادثة مفتوحة", "open incident(s)")}</span>`
          : `<span class="badge bg-success-subtle text-success">${governanceText("سليم", "Clear")}</span>`;

        const priorityBadge = subRate < 40 || openIncidents > 0
          ? `<span class="badge bg-danger px-2 py-1">${governanceText("حرج جداً", "High Risk")}</span>`
          : `<span class="badge bg-warning text-dark px-2 py-1">${governanceText("تحت المتابعة", "Needs Review")}</span>`;

        const lastDate = lp.last_submission_date
          ? new Date(lp.last_submission_date).toLocaleDateString(governanceLocale())
          : "--";

        return `
          <tr>
            <td class="text-center">${priorityBadge}</td>
            <td><div class="fw-bold text-dark">${kgName}</div>${govBadge}</td>
            <td class="text-center"><span class="fw-bold text-danger">${subRate}%</span></td>
            <td class="text-center"><span class="badge bg-danger-subtle text-danger fs-6">${lp.gap || 0} ${governanceText("تقرير", "reports")}</span></td>
            <td class="text-center">${lp.rejection_rate != null ? `${Number(lp.rejection_rate).toFixed(1)}%` : "--"}</td>
            <td class="text-center">${safeguardingBadge}</td>
            <td class="text-center small text-muted">${lastDate}</td>
            <td class="text-center fw-semibold">${lp.reminder_count || 0}</td>
            <td class="text-end pe-3">
              <button class="btn btn-sm btn-danger js-reminder-btn"
                      data-target-type="kindergarten"
                      data-target-id="${lp.kindergarten_id}"
                      data-target-name="${kgName}">
                  <i class="bi bi-bell-fill me-1"></i>${governanceText("إرسال تذكير عاجل", "Send Urgent Reminder")}
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  }
}

// ─── Reminders ───────────────────────────────────────────────────────────

function renderReminders(items) {
  const tbody = document.getElementById("remindersBody");
  if (!items || items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">${governanceText("لا توجد تذكيرات", "No reminders")}</td></tr>`;
    return;
  }
  tbody.innerHTML = items
    .map(
      (r) => {
        const targetLabel = r.governorate ? `#${r.target_id} <span class="badge bg-light text-dark ms-1">${escapeHtml(r.governorate)}</span>` : `#${r.target_id}`;
        return `
        <tr>
            <td>${r.target_type === "kindergarten" ? governanceText("حضانة", "Kindergarten") : governanceText("مشرف", "Supervisor")}</td>
            <td>${targetLabel}</td>
            <td>${escapeHtml(formatReminderType(r.reminder_type))}</td>
            <td>${r.sent_at ? new Date(r.sent_at).toLocaleString(governanceLocale()) : "--"}</td>
            <td>${r.cooldown_expires_at ? new Date(r.cooldown_expires_at).toLocaleString(governanceLocale()) : "--"}</td>
        </tr>
    `;
      }
    )
    .join("");
}

async function loadReminders() {
  try {
    const reminders = await governanceFetch(
      `/api/admin/governance/reminders?page=${remindersPage}&page_size=${REMINDERS_PAGE_SIZE}`
    );
    remindersTotal = reminders.total || 0;
    renderReminders(reminders.items);
    renderRemindersPagination();
  } catch (err) {
    console.error("Failed to load reminders", err);
  }
}

function renderRemindersPagination() {
  const nav = document.getElementById("remindersPagination");
  if (!nav) return;
  const totalPages = Math.max(1, Math.ceil(remindersTotal / REMINDERS_PAGE_SIZE));
  if (totalPages <= 1) {
    nav.innerHTML = "";
    return;
  }
  nav.innerHTML = `
    <button type="button" class="btn btn-sm btn-outline-secondary" id="remindersPrevBtn"
            aria-label="${governanceText('الصفحة السابقة', 'Previous page')}" ${remindersPage <= 1 ? "disabled" : ""}>
      <i class="bi bi-chevron-left icon-directional" aria-hidden="true"></i>
    </button>
    <span class="small text-muted mx-3">${governanceText(`صفحة ${remindersPage} من ${totalPages}`, `Page ${remindersPage} of ${totalPages}`)}</span>
    <button type="button" class="btn btn-sm btn-outline-secondary" id="remindersNextBtn"
            aria-label="${governanceText('الصفحة التالية', 'Next page')}" ${remindersPage >= totalPages ? "disabled" : ""}>
      <i class="bi bi-chevron-right icon-directional" aria-hidden="true"></i>
    </button>`;
  document.getElementById("remindersPrevBtn")?.addEventListener("click", () => {
    if (remindersPage > 1) {
      remindersPage--;
      loadReminders();
    }
  });
  document.getElementById("remindersNextBtn")?.addEventListener("click", () => {
    if (remindersPage < totalPages) {
      remindersPage++;
      loadReminders();
    }
  });
}

// ─── Reminder Modal ──────────────────────────────────────────────────────

function openReminderModal(targetType, targetId, targetName) {
  _reminderTarget = { type: targetType, id: targetId };
  document.getElementById("reminderTargetName").textContent = targetName || `#${targetId}`;
  new bootstrap.Modal(document.getElementById("reminderModal")).show();
}

const confirmReminderBtn = document.getElementById("confirmReminderBtn");
if (confirmReminderBtn) {
  confirmReminderBtn.addEventListener("click", async () => {
    if (!_reminderTarget) return;
    const btn = confirmReminderBtn;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${governanceText("جاري الإرسال...", "Sending...")}`;

    try {
      await governanceFetch("/api/admin/governance/reminders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_type: _reminderTarget.type,
          target_id: _reminderTarget.id,
          reminder_type: "low_submission_rate",
        }),
      });
      bootstrap.Modal.getInstance(document.getElementById("reminderModal")).hide();
      showMessage({
        icon: "success",
        title: governanceText("تم الإرسال", "Sent"),
        text: governanceText("تم إرسال التذكير بنجاح", "Reminder sent successfully"),
        timer: 2000,
      });
      loadGovernanceData();
    } catch (err) {
      const detail = err?.body?.detail;
      const msg =
        (typeof detail === "string" && detail) ||
        detail?.message ||
        err?.message ||
        governanceText("فشل إرسال التذكير", "Failed to send reminder");
      showMessage({
        icon: "error",
        title: governanceText("خطأ", "Error"),
        text: msg,
      });
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<i class="bi bi-bell me-1"></i>${governanceText("إرسال", "Send")}`;
    }
  });
}

// ─── Init ────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest(".js-reminder-btn");
    if (!trigger) return;
    const targetType = trigger.dataset.targetType || "kindergarten";
    const targetId = Number(trigger.dataset.targetId || 0);
    const targetName = trigger.dataset.targetName || `#${targetId}`;
    if (!targetId) return;
    openReminderModal(targetType, targetId, targetName);
  });

  const today = new Date();
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  document.getElementById("endDate").value = today.toISOString().split("T")[0];
  document.getElementById("startDate").value = weekAgo.toISOString().split("T")[0];

  loadGovernanceData();
});

window.addEventListener("languageChanged", () => {
  if (document.getElementById("startDate") && document.getElementById("endDate")) {
    loadGovernanceData();
  }
});

function exportGovernanceCSV() {
  const tbody = document.getElementById("leaderboardBody");
  if (!tbody) return;
  const rows = Array.from(tbody.querySelectorAll("tr"));
  if (!rows.length || rows[0].cells.length < 5) {
    showMessage({
      icon: "warning",
      title: governanceText("لا توجد بيانات", "No Data"),
      text: governanceText("لا توجد بيانات متاحة للتصدير.", "No data available for export."),
    });
    return;
  }

  const headers = [
    "#",
    governanceText("الحضانة", "Kindergarten"),
    governanceText("مطلوب", "Required"),
    governanceText("مقدم", "Submitted"),
    governanceText("مسلم", "Delivered"),
    governanceText("مشاهد", "Viewed"),
    governanceText("خام%", "Raw%"),
    governanceText("النتيجة", "Score"),
    governanceText("رفض%", "Rejection%"),
    governanceText("صباح%", "Morning%"),
    governanceText("اتساق", "Consistency"),
    governanceText("متوسط موافقة", "Avg Approval"),
    governanceText("آخر تقرير", "Last Report"),
    governanceText("تذكيرات", "Reminders")
  ];

  const csvRows = [headers.join(",")];
  rows.forEach(tr => {
    const cells = Array.from(tr.querySelectorAll("td"));
    if (cells.length >= 14) {
      const rowData = cells.slice(0, 14).map(td => {
        let val = td.innerText.replace(/\n/g, " ").trim();
        return `"${val.replace(/"/g, '""')}"`;
      });
      csvRows.push(rowData.join(","));
    }
  });

  const blob = new Blob(["\uFEFF" + csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const filename = `governance_report_${document.getElementById("startDate").value || "start"}_${document.getElementById("endDate").value || "end"}.csv`;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
