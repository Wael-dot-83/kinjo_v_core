/**
 * Admin Governance Reports — Daily Report Compliance Dashboard
 */

let funnelChart = null;
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
    const query = new URLSearchParams({
      start_date: start,
      end_date: end,
    }).toString();

    const [kpis, board, reminders] = await Promise.all([
      governanceFetch(`/api/admin/governance/kpis?${query}`),
      governanceFetch(`/api/admin/governance/leaderboard?${query}`),
      governanceFetch(`/api/admin/governance/reminders?page=1&page_size=10`),
    ]);
    renderKPICards(kpis);
    renderFunnelChart(kpis.funnel);
    renderTimeliness(kpis.timeliness, kpis.consistency);
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

  // Quality from first KG aggregate
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
          backgroundColor: ["#6c757d", "#1F5E47", "#198754", "#B49B3B"],
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

// ─── Leaderboard ─────────────────────────────────────────────────────────

function renderLeaderboard(entries) {
  const tbody = document.getElementById("leaderboardBody");
  if (!entries || entries.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" class="text-center text-muted py-4">${governanceText("لا توجد بيانات كافية", "Insufficient data")}</td></tr>`;
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
      return `<tr>
            <td><span class="rank-badge ${rankClass}">${e.rank}</span></td>
            <td>${kgName} ${lowBadge}</td>
            <td>${e.required}</td>
            <td>${e.submitted}</td>
            <td>${e.delivered}</td>
            <td>${e.viewed}</td>
            <td>${formatPercent(e.raw_rate)}</td>
            <td><strong>${formatPercent(e.bayesian_score)}</strong></td>
            <td>
                <button class="btn btn-sm btn-outline-warning js-reminder-btn"
                        data-target-type="kindergarten"
                        data-target-id="${e.kindergarten_id}"
                        data-target-name="${kgName}">
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
