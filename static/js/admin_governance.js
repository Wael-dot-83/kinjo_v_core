/**
 * Admin Governance Reports — Daily Report Compliance Dashboard
 */

let funnelChart = null;
let trendChart = null;
let _reminderTarget = null;

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

const REMINDER_TYPE_LABELS = {
  low_submission_rate: governanceText("انخفاض نسبة التقديم", "Low submission rate"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

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

function formatReminderType(reminderType) {
  return REMINDER_TYPE_LABELS[reminderType] || reminderType || "--";
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
      refreshBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>${governanceText("جاري التحميل...", "Loading...")}`;
    }
    const query = new URLSearchParams({ start_date: start, end_date: end }).toString();

    const [kpis, board, reminders, trend, safeguarding] = await Promise.all([
      governanceFetch(`/api/admin/governance/kpis?${query}`),
      governanceFetch(`/api/admin/governance/leaderboard?${query}`),
      governanceFetch(`/api/admin/governance/reminders?page=1&page_size=10`),
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
    renderReminders(reminders.items);
  } catch (err) {
    console.error("Failed to load governance data", err);
    const detail = err?.body?.detail;
    const message =
      (typeof detail === "string" && detail) ||
      detail?.message ||
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

function renderLeaderboard(entries) {
  const tbody = document.getElementById("leaderboardBody");
  if (!entries || entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="15" class="text-center text-muted py-4">${governanceText("لا توجد بيانات كافية", "Insufficient data")}</td></tr>`;
    return;
  }

  tbody.innerHTML = entries
    .map((e) => {
      const rankClass = e.rank <= 3 ? `rank-${e.rank}` : "rank-default";
      const kgNameRaw = e.name_ar || e.name_en || `KG#${e.kindergarten_id}`;
      const kgName = escapeHtml(governanceLiteral(kgNameRaw));
      const lowBadge = e.is_low_performer
        ? `<span class="badge bg-warning text-dark ms-1">${governanceText("ضعيف", "Weak")}</span>`
        : "";
      const rejRate = e.rejection_rate != null ? `${e.rejection_rate}%` : "--";
      const morRate = e.morning_rate != null ? `${e.morning_rate}%` : "--";
      const ciVal = e.consistency_index != null ? `${e.consistency_index}%` : "--";
      const approvalH = e.avg_approval_hours != null ? formatHours(e.avg_approval_hours) : "--";
      const lastDate = e.last_report_date
        ? new Date(e.last_report_date).toLocaleDateString(governanceLocale())
        : "--";
      const reminderCnt = e.reminder_count != null ? e.reminder_count : "--";

      return `<tr>
          <td><span class="rank-badge ${rankClass}">${e.rank}</span></td>
          <td>${kgName} ${lowBadge}</td>
          <td>${e.required}</td>
          <td>${e.submitted}</td>
          <td>${e.delivered}</td>
          <td>${e.viewed}</td>
          <td>${formatPercent(e.raw_rate)}</td>
          <td><strong>${formatPercent(e.bayesian_score)}</strong></td>
          <td><span class="${e.rejection_rate > 15 ? 'text-danger fw-bold' : ''}">${rejRate}</span></td>
          <td>${morRate}</td>
          <td>${ciVal}</td>
          <td>${approvalH}</td>
          <td>${lastDate}</td>
          <td>${reminderCnt}</td>
          <td>
              <button class="btn btn-sm btn-outline-warning js-reminder-btn"
                      data-target-type="kindergarten"
                      data-target-id="${e.kindergarten_id}"
                      data-target-name="${kgName}"
                      title="${governanceText('إرسال تذكير', 'Send reminder')}">
                  <i class="bi bi-bell"></i>
              </button>
          </td>
      </tr>`;
    })
    .join("");
}

// ─── Low Performers ──────────────────────────────────────────────────────

function renderLowPerformers(items) {
  const section = document.getElementById("lowPerformersSection");
  const container = document.getElementById("lowPerformersList");
  if (!items || items.length === 0) {
    section.classList.add("d-none");
    return;
  }
  section.classList.remove("d-none");
  container.innerHTML = items
    .map((lp) => {
      const kgNameRaw = lp.name_ar || lp.name_en || `KG#${lp.kindergarten_id}`;
      const kgName = escapeHtml(governanceLiteral(kgNameRaw));
      return `
        <div class="col-md-4">
            <div class="low-performer-badge p-3">
                <div class="fw-bold">${kgName}</div>
                <div class="text-muted small">${governanceText("نسبة التقديم", "Submission rate")}: ${formatPercent(lp.submission_rate)}</div>
                <div class="text-muted small">${governanceText("الفجوة", "Gap")}: ${lp.gap} ${governanceText("تقرير", "reports")}</div>
                <button class="btn btn-sm btn-warning mt-2 js-reminder-btn"
                        data-target-type="kindergarten"
                        data-target-id="${lp.kindergarten_id}"
                        data-target-name="${kgName}">
                    <i class="bi bi-bell me-1"></i>${governanceText("إرسال تذكير", "Send reminder")}
                </button>
            </div>
        </div>
    `;
    })
    .join("");
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
      (r) => `
        <tr>
            <td>${r.target_type === "kindergarten" ? governanceText("روضة", "Kindergarten") : governanceText("مشرف", "Supervisor")}</td>
            <td>#${r.target_id}</td>
            <td>${escapeHtml(formatReminderType(r.reminder_type))}</td>
            <td>${r.sent_at ? new Date(r.sent_at).toLocaleString(governanceLocale()) : "--"}</td>
            <td>${r.cooldown_expires_at ? new Date(r.cooldown_expires_at).toLocaleString(governanceLocale()) : "--"}</td>
        </tr>
    `
    )
    .join("");
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
