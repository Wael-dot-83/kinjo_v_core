/**
 * Admin Kindergarten Overview JavaScript
 * Handles data fetching, KPI rendering, charts, and interactive functionality
 */

(function () {
  const API = "/api/admin/kg-overview";

  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function i18n(ar, en) {
    if (window.AppI18n && typeof window.AppI18n.t === "function") {
      const key = AppI18n.t(ar);
      if (key && key !== ar) return key;
    }
    return document.documentElement.lang === "en" ? en : ar;
  }

  function statusBadge(status) {
    const map = {
      on_target: "success",
      below_target: "warning",
      critical_low: "danger",
      safe: "success",
      monitor: "info",
      near_capacity: "warning",
      full: "danger",
      updated: "success",
      needs_update: "warning",
      excellent: "success",
      good: "info",
      needs_attention: "warning",
      at_risk: "danger",
      critical: "danger",
    };
    const labelMap = {
      on_target: i18n("على الهدف", "On Target"),
      below_target: i18n("أقل من الهدف", "Below Target"),
      critical_low: i18n("منخفض جداً", "Critical Low"),
      safe: i18n("آمن", "Safe"),
      monitor: i18n("تحت المتابعة", "Monitor"),
      near_capacity: i18n("قريب من الامتلاء", "Near Capacity"),
      full: i18n("ممتلئ", "Full"),
      updated: i18n("محدث", "Updated"),
      needs_update: i18n("يحتاج تحديث", "Needs Update"),
      excellent: i18n("ممتاز", "Excellent"),
      good: i18n("جيد", "Good"),
      needs_attention: i18n("يحتاج متابعة", "Needs Attention"),
      at_risk: i18n("معرّض للخطر", "At Risk"),
      critical: i18n("حرج", "Critical"),
    };
    const cls = map[status] || "secondary";
    const label = labelMap[status] || status;
    return `<span class="badge bg-${cls}">${escapeHtml(label)}</span>`;
  }

  function severityBadge(severity) {
    const map = { CRITICAL: "danger", HIGH: "warning", MEDIUM: "info", LOW: "secondary" };
    const labelMap = { CRITICAL: i18n("حرج", "Critical"), HIGH: i18n("عالي", "High"), MEDIUM: i18n("متوسط", "Medium"), LOW: i18n("منخفض", "Low") };
    return `<span class="badge bg-${map[severity] || 'secondary'}">${escapeHtml(labelMap[severity] || severity)}</span>`;
  }

  function ageLabel(hours) {
    if (hours == null) return "-";
    if (hours < 1) return i18n("أقل من ساعة", "< 1h");
    if (hours < 24) return `${Math.round(hours)}h`;
    return `${Math.round(hours / 24)}d`;
  }

  function renderExecutiveHealth(health) {
    const el = document.getElementById("executive-health-banner");
    const txt = document.getElementById("executive-health-text");
    if (!el || !txt) return;
    const parts = [];
    if (health.critical_alerts > 0) parts.push(i18n(`${health.critical_alerts} تنبيهات حرجة تحتاج مراجعة فورية`, `${health.critical_alerts} critical alerts need immediate review`));
    if (health.near_capacity_kgs > 0) parts.push(i18n(`${health.near_capacity_kgs} روضات قريبة من الطاقة القصوى`, `${health.near_capacity_kgs} kindergartens near capacity`));
    if (health.below_target_attendance > 0) parts.push(i18n(`${health.below_target_attendance} روضات أقل من حد الحضور المقبول`, `${health.below_target_attendance} kindergartens below attendance target`));
    if (health.data_quality_issues > 0) parts.push(i18n(`${health.data_quality_issues} روضات تحتاج تحديث بيانات`, `${health.data_quality_issues} kindergartens need data updates`));
    txt.innerHTML = parts.join(" | ");
    el.style.display = parts.length ? "block" : "none";
  }

  function renderKPIs(kpis) {
    const container = document.getElementById("kpi-cards");
    if (!container) return;
    container.innerHTML = kpis.map((kpi, idx) => {
      const trendHtml = kpi.trend ? `<small class="text-muted d-block">${escapeHtml(kpi.trend)}</small>` : "";
      const detailHtml = kpi.details ? `<small class="${kpi.details.note_en && kpi.details.note_en.toLowerCase().includes('below') || kpi.details.note_ar && kpi.details.note_ar.includes('أقل') ? 'text-danger' : 'text-muted'} d-block mt-1">${escapeHtml(document.documentElement.lang === 'en' ? kpi.details.note_en : kpi.details.note_ar)}</small>` : "";
      const statusClass = kpi.status === "critical" ? "border-danger" : kpi.status === "warning" ? "border-warning" : "border-success";
      return `
        <div class="col-md-6 col-xl-3">
          <div class="card admin-card h-100 border-start border-4 ${statusClass}">
            <div class="card-body">
              <h6 class="text-muted mb-2">${escapeHtml(document.documentElement.lang === 'en' ? kpi.title_en : kpi.title_ar)}</h6>
              <div class="d-flex align-items-baseline">
                <h3 class="mb-0 fw-bold">${kpi.value}</h3>
                ${kpi.unit ? `<span class="ms-1 text-muted">${escapeHtml(kpi.unit)}</span>` : ''}
              </div>
              ${trendHtml}
              ${detailHtml}
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderTable(kgs) {
    const tbody = document.getElementById("kg-table-body");
    if (!tbody) return;
    if (!kgs.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="text-center py-4 text-muted">${escapeHtml(i18n("لا توجد بيانات", "No data"))}</td></tr>`;
      return;
    }
    tbody.innerHTML = kgs.map(kg => `
      <tr>
        <td class="fw-semibold">${escapeHtml(kg.name_ar)} ${kg.name_en ? `<small class="text-muted">(${escapeHtml(kg.name_en)})</small>` : ''}</td>
        <td>${escapeHtml(kg.governorate)}</td>
        <td>${kg.children_count}</td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <span>${kg.attendance_rate}%</span>
            ${statusBadge(kg.attendance_status)}
          </div>
        </td>
        <td>
          <div class="d-flex align-items-center gap-2">
            <span>${kg.occupancy_rate}%</span>
            ${statusBadge(kg.occupancy_status)}
          </div>
        </td>
        <td>${kg.teachers_count}</td>
        <td>${kg.open_alerts}</td>
        <td>${statusBadge(kg.health_score)} <small class="text-muted">${escapeHtml(document.documentElement.lang === 'en' ? kg.health_label_en : kg.health_label_ar)}</small></td>
        <td>
          <a href="/kindergartens/${kg.id}" class="btn btn-sm btn-outline-primary" title="${escapeHtml(i18n('عرض التفاصيل', 'View Details'))}">
            <i class="bi bi-eye"></i>
          </a>
        </td>
      </tr>
    `).join("");
  }

  function renderCards(kgs) {
    const container = document.getElementById("kg-cards-container");
    if (!container) return;
    if (!kgs.length) {
      container.innerHTML = `<div class="col-12 text-center py-4 text-muted">${escapeHtml(i18n("لا توجد بيانات", "No data"))}</div>`;
      return;
    }
    container.innerHTML = kgs.map(kg => {
      const colorClass = kg.health_score === 'critical' ? 'border-danger' : kg.health_score === 'at_risk' ? 'border-danger' : kg.health_score === 'needs_attention' ? 'border-warning' : 'border-success';
      return `
        <div class="col-md-6 col-lg-4">
          <div class="card admin-card h-100 border-start border-4 ${colorClass}">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start mb-2">
                <div>
                  <h5 class="card-title mb-0">${escapeHtml(kg.name_ar)}</h5>
                  <small class="text-muted">${escapeHtml(kg.governorate)} · ${escapeHtml(kg.city)}</small>
                </div>
                ${statusBadge(kg.health_score)}
              </div>
              <div class="row g-2 mt-2">
                <div class="col-6"><strong>${escapeHtml(i18n('الأطفال', 'Children'))}:</strong> ${kg.children_count}</div>
                <div class="col-6"><strong>${escapeHtml(i18n('الحضور', 'Attendance'))}:</strong> ${kg.attendance_rate}% ${statusBadge(kg.attendance_status)}</div>
                <div class="col-6"><strong>${escapeHtml(i18n('الإشغال', 'Occupancy'))}:</strong> ${kg.occupancy_rate}% ${statusBadge(kg.occupancy_status)}</div>
                <div class="col-6"><strong>${escapeHtml(i18n('المعلمات', 'Teachers'))}:</strong> ${kg.teachers_count}</div>
                <div class="col-6"><strong>${escapeHtml(i18n('التنبيهات', 'Alerts'))}:</strong> ${kg.open_alerts}</div>
                <div class="col-6"><strong>${escapeHtml(i18n('آخر تقرير', 'Last Report'))}:</strong> ${kg.last_report_date ? escapeHtml(kg.last_report_date) : '-'} ${statusBadge(kg.teacher_data_status)}</div>
              </div>
              <div class="mt-3 p-2 bg-light rounded small">
                <strong>${escapeHtml(i18n('الإجراء المقترح', 'Recommended Action'))}:</strong>
                ${escapeHtml(document.documentElement.lang === 'en' ? kg.recommended_action_en : kg.recommended_action_ar)}
              </div>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  function renderAlerts(alerts, severityFilter) {
    const tbody = document.getElementById("alerts-table-body");
    if (!tbody) return;
    const filtered = severityFilter ? alerts.filter(a => a.severity === severityFilter) : alerts;
    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">${escapeHtml(i18n("لا توجد تنبيهات", "No alerts"))}</td></tr>`;
      return;
    }
    tbody.innerHTML = filtered.map(a => `
      <tr>
        <td>${severityBadge(a.severity)}</td>
        <td>${a.kindergarten_name_ar ? escapeHtml(a.kindergarten_name_ar) : '-'}</td>
        <td>${escapeHtml(a.message)}</td>
        <td>${escapeHtml(a.metric)}</td>
        <td>${a.current_value}</td>
        <td>${ageLabel(a.age_hours)}</td>
        <td>
          <div class="btn-group btn-group-sm">
            <button class="btn btn-outline-primary btn-sm" onclick="window.open('/kindergartens/${a.kindergarten_id || ''}', '_blank')" ${!a.kindergarten_id ? 'disabled' : ''}>
              <i class="bi bi-eye"></i>
            </button>
            <button class="btn btn-outline-warning btn-sm" onclick="this.closest('tr').style.display='none'" title="${escapeHtml(i18n('تجاهل', 'Dismiss'))}">
              <i class="bi bi-x-circle"></i>
            </button>
          </div>
        </td>
      </tr>
    `).join("");
  }

  function renderCharts(data) {
    const lang = document.documentElement.lang === "en" ? "en" : "ar";
    const commonOptions = { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: "bottom" } } };

    // Attendance chart (horizontal bar)
    if (data.attendance_by_kg && data.attendance_by_kg.length) {
      const ctx = document.getElementById("attendance-chart");
      if (ctx) {
        new Chart(ctx, {
          type: "bar",
          data: {
            labels: data.attendance_by_kg.map(p => lang === 'en' && p.name_en ? p.name_en : p.name_ar || p.name),
            datasets: [{
              label: i18n("نسبة الحضور", "Attendance %"),
              data: data.attendance_by_kg.map(p => p.value),
              backgroundColor: data.attendance_by_kg.map(p => p.value < 70 ? "rgba(220,53,69,0.7)" : p.value < 80 ? "rgba(255,193,7,0.7)" : "rgba(40,167,69,0.7)"),
            }],
          },
          options: { ...commonOptions, indexAxis: "y", scales: { x: { beginAtZero: true, max: 100 } } },
        });
      }
    }

    // Occupancy chart
    if (data.occupancy_pressure && data.occupancy_pressure.length) {
      const ctx = document.getElementById("occupancy-chart");
      if (ctx) {
        new Chart(ctx, {
          type: "bar",
          data: {
            labels: data.occupancy_pressure.map(p => lang === 'en' && p.name_en ? p.name_en : p.name_ar || p.name),
            datasets: [{
              label: i18n("نسبة الإشغال", "Occupancy %"),
              data: data.occupancy_pressure.map(p => p.value),
              backgroundColor: data.occupancy_pressure.map(p => p.value < 70 ? "rgba(40,167,69,0.7)" : p.value < 85 ? "rgba(255,193,7,0.7)" : p.value < 95 ? "rgba(255,152,0,0.7)" : "rgba(220,53,69,0.7)"),
            }],
          },
          options: commonOptions,
        });
      }
    }

    // Alerts by severity donut
    if (data.alerts_by_severity && data.alerts_by_severity.length) {
      const ctx = document.getElementById("alerts-severity-chart");
      if (ctx) {
        new Chart(ctx, {
          type: "doughnut",
          data: {
            labels: data.alerts_by_severity.map(p => p.name_ar || p.name),
            datasets: [{
              data: data.alerts_by_severity.map(p => p.value),
              backgroundColor: ["rgba(220,53,69,0.7)", "rgba(255,152,0,0.7)", "rgba(255,193,7,0.7)", "rgba(108,117,125,0.7)"],
            }],
          },
          options: commonOptions,
        });
      }
    }

    // Governorate comparison
    if (data.governorate_comparison && data.governorate_comparison.length) {
      const ctx = document.getElementById("governorate-chart");
      if (ctx) {
        new Chart(ctx, {
          type: "bar",
          data: {
            labels: data.governorate_comparison.map(g => g.name_ar || g.name),
            datasets: [
              {
                label: i18n("نسبة الحضور", "Attendance %"),
                data: data.governorate_comparison.map(g => g.attendance_rate),
                backgroundColor: "rgba(40,167,69,0.7)",
              },
              {
                label: i18n("الإشغال", "Occupancy %"),
                data: data.governorate_comparison.map(g => g.occupancy_rate),
                backgroundColor: "rgba(54,162,235,0.7)",
              },
            ],
          },
          options: commonOptions,
        });
      }
    }

    // Alerts by type chart
    if (data.alerts_by_type && data.alerts_by_type.length) {
      const ctx = document.getElementById("alerts-type-chart");
      if (ctx) {
        new Chart(ctx, {
          type: "bar",
          data: {
            labels: data.alerts_by_type.map(p => p.name_ar || p.name),
            datasets: [{
              label: i18n("عدد التنبيهات", "Alert Count"),
              data: data.alerts_by_type.map(p => p.value),
              backgroundColor: "rgba(153,102,255,0.7)",
            }],
          },
          options: commonOptions,
        });
      }
    }
  }

  function showLoading() {
    document.querySelectorAll(".spinner-border").forEach(el => el.style.display = "");
    document.querySelectorAll('[style*="display: none"]') // noop
  }

  function hideLoading() {
    // Charts and tables handle their own loading state via spinner replacement
  }

  async function loadOverview() {
    const period = document.getElementById("kg-period")?.value || "month";
    const governorate = document.getElementById("kg-governorate")?.value || "";
    const riskLevel = document.getElementById("kg-risk")?.value || "";

    const params = new URLSearchParams({ period, governorate, risk_level: riskLevel });
    try {
      const response = await fetch(`${API}?${params.toString()}`, {
        method: "GET",
        headers: { "Accept": "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();

      renderKPIs(data.kpis || []);
      renderExecutiveHealth(data.executive_health || {});
      renderTable(data.kindergartens || []);
      renderCards(data.kindergartens || []);
      renderCharts(data.charts || {});
      renderAlerts(data.alerts || [], "");

      // Populate governorate dropdown
      populateGovernorates(data.kindergartens || []);
      const errorEl = document.getElementById("kg-overview-error");
      if (errorEl) errorEl.style.display = "none";
    } catch (err) {
      console.error("Error loading kg overview:", err);
      const errorEl = document.getElementById("kg-overview-error");
      if (errorEl) {
        errorEl.style.display = "block";
        const textEl = document.getElementById("kg-overview-error-text");
        if (textEl) textEl.textContent = `${escapeHtml(i18n("خطأ في تحميل البيانات:", "Error loading data:"))} ${escapeHtml(err.message || String(err))}`;
      }
    }
  }

  function populateGovernorates(kgs) {
    const select = document.getElementById("kg-governorate");
    if (!select) return;
    const current = select.value;
    const govs = Array.from(new Set(kgs.map(k => k.governorate).filter(Boolean))).sort();
    select.innerHTML = `<option value="">${escapeHtml(i18n("جميع المحافظات", "All Governorates"))}</option>` +
      govs.map(g => `<option value="${escapeHtml(g)}" ${g === current ? 'selected' : ''}>${escapeHtml(g)}</option>`).join("");
  }

  function initTabs() {
    const buttons = document.querySelectorAll('[data-tab]');
    buttons.forEach(btn => {
      btn.addEventListener("click", () => {
        buttons.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.getAttribute("data-tab");
        document.getElementById("kg-table-view").style.display = tab === "table" ? "" : "none";
        document.getElementById("kg-cards-view").style.display = tab === "cards" ? "" : "none";
      });
    });
  }

  function initAlertFilters() {
    const buttons = document.querySelectorAll("#alert-filter-group button");
    buttons.forEach(btn => {
      btn.addEventListener("click", async () => {
        buttons.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const sev = btn.getAttribute("data-severity");
        // Re-fetch and filter locally for speed, or re-render with filter
        // For now, we rely on the server-side filter in loadOverview, so just re-apply visual filter
        const rows = document.querySelectorAll("#alerts-table-body tr");
        let visible = 0;
        rows.forEach(row => {
          if (!sev) { row.style.display = ""; visible++; return; }
          const badge = row.querySelector(".badge");
          const sevText = badge ? badge.textContent.trim() : "";
          const match = sev === sevText || (sev === "HIGH" && sevText === "عالي") || (sev === "CRITICAL" && sevText === "حرج") || (sev === "MEDIUM" && sevText === "متوسط") || (sev === "LOW" && sevText === "منخفض");
          row.style.display = match ? "" : "none";
          if (match) visible++;
        });
        if (!visible) {
          document.getElementById("alerts-table-body").innerHTML = `<tr><td colspan="7" class="text-center py-4 text-muted">${escapeHtml(i18n("لا توجد تنبيهات", "No alerts"))}</td></tr>`;
        }
      });
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    initTabs();
    initAlertFilters();

    document.getElementById("refresh-kg-overview")?.addEventListener("click", loadOverview);
    document.getElementById("apply-kg-filters")?.addEventListener("click", loadOverview);

    loadOverview();
  });

  window.adminKgOverview = { loadOverview, renderTable, renderCards, renderCharts };
})();
