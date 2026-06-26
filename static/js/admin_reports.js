// admin_reports.js — Enterprise Reports Center logic
// Requires: Chart.js, chart_utils.js, sanitize.js, admin_analytics.js loaded beforehand.

(function () {
  "use strict";

  if (window.AdminReports) return;
  window.AdminReports = {};

  const API_BASE = "/api/analytics";

  // ===========================================================================
  // Helpers
  // ===========================================================================
  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function reportsText(ar, en) {
    const lang = document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    return lang === "en" ? en : ar;
  }

  function getEl(id) {
    return document.getElementById(id);
  }

  function setText(id, text) {
    const el = getEl(id);
    if (!el) return;
    el.innerText = text;
  }

  function showEl(id) {
    const el = getEl(id);
    if (el) el.classList.remove("d-none");
  }

  function hideEl(id) {
    const el = getEl(id);
    if (el) el.classList.add("d-none");
  }

  function getPeriod() {
    return {
      start: getEl("periodStart")?.value || "",
      end: getEl("periodEnd")?.value || "",
    };
  }

  function getGovernorate() {
    return getEl("governorateFilter")?.value || "";
  }

  function getFilters() {
    return {
      governorate: getGovernorate(),
      kindergarten_id: getEl("kindergartenFilter")?.value ? Number(getEl("kindergartenFilter").value) : null,
      status: getEl("statusFilter")?.value || null,
      severity: getEl("severityFilter")?.value || null,
      source: getEl("sourceFilter")?.value || null,
      reviewer_id: getEl("reviewerFilter")?.value ? Number(getEl("reviewerFilter").value) : null,
    };
  }

  function getReportType() {
    const activeTab = document.querySelector("#reportCategoryTabs .nav-link.active");
    if (activeTab) {
      const target = activeTab.getAttribute("data-bs-target");
      if (target === "#pane-incidents") return "incidents";
      if (target === "#pane-compliance") return "compliance";
      if (target === "#pane-enrollment") return "enrollment";
      if (target === "#pane-audit") return "full_audit";
    }
    return "attendance";
  }

  async function fetchWithAuth(url, options) {
    const method = (options?.method || "GET").toUpperCase();
    const opts = Object.assign({ credentials: "same-origin" }, options || {});
    opts.headers = Object.assign({ "Accept": "application/json" }, opts.headers || {});
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      const csrfToken =
        (window.CSRF_CONFIG && window.CSRF_CONFIG.cookieName && window.AuthStorage && window.AuthStorage.getCookie && window.AuthStorage.getCookie(window.CSRF_CONFIG.cookieName)) ||
        document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
        "";
      if (csrfToken) {
        opts.headers["X-CSRF-Token"] = csrfToken;
      }
    }
    const response = await fetch(url, opts);
    if (response.status === 401) {
      window.location.href = "/login?redirect=" + encodeURIComponent(window.location.pathname);
      return null;
    }
    if (!response.ok) {
      const err = new Error(response.statusText || `Request failed with status ${response.status}`);
      err.status = response.status;
      throw err;
    }
    return response;
  }

  function destroyChartInstances() {
    const ids = ["funnelChart", "sourceChart", "trendChart", "governancePieChart"];
    ids.forEach((id) => {
      const canvas = document.getElementById(id);
      if (!canvas) return;
      const chart = window.Chart.getChart(canvas);
      if (chart) chart.destroy();
    });
  }

  // ===========================================================================
  // Governorate & Kindergarten population
  // ===========================================================================
  async function loadGovernorates() {
    const select = getEl("governorateFilter");
    if (!select) return;
    try {
      const res = await fetchWithAuth("/api/admin/options/governorates");
      if (!res) return;
      const data = await res.json();
      const list = data.governorates || [];
      // keep first option
      while (select.options.length > 1) select.remove(1);
      list.forEach((g) => {
        const opt = document.createElement("option");
        opt.value = g.value || g;
        opt.textContent = g.label || g;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load governorates", e);
    }
  }

  async function loadKindergartens() {
    const select = getEl("kindergartenFilter");
    if (!select) return;
    try {
      const gov = getGovernorate();
      const url = gov ? `/api/admin/options/kindergartens?governorate=${encodeURIComponent(gov)}` : "/api/admin/options/kindergartens";
      const res = await fetchWithAuth(url);
      if (!res) return;
      const data = await res.json();
      const list = data.kindergartens || [];
      while (select.options.length > 1) select.remove(1);
      list.forEach((kg) => {
        const opt = document.createElement("option");
        opt.value = kg.id || kg;
        opt.textContent = kg.name_ar || kg.name_en || kg;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load kindergartens", e);
    }
  }

  async function loadReviewers() {
    const select = getEl("reviewerFilter");
    if (!select) return;
    try {
      const res = await fetchWithAuth("/api/admin/users?role=MANAGER&limit=100");
      if (!res) return;
      const data = await res.json();
      const users = data.data || [];
      while (select.options.length > 1) select.remove(1);
      users.forEach((u) => {
        const opt = document.createElement("option");
        opt.value = u.id;
        opt.textContent = u.full_name || u.username;
        select.appendChild(opt);
      });
    } catch (e) {
      console.error("Failed to load reviewers", e);
    }
  }

  async function loadStatuses() {
    const select = getEl("statusFilter");
    if (!select) return;
    const fallback = [
      { value: "DRAFT", label_ar: "غير مكتمل", label_en: "Incomplete" },
      { value: "SUBMITTED", label_ar: "قيد التحقق", label_en: "Under Verification" },
      { value: "PENDING_REVIEW", label_ar: "قيد المراجعة", label_en: "Pending Review" },
      { value: "ACCEPTED", label_ar: "موافق عليه", label_en: "Approved" },
      { value: "REJECTED", label_ar: "مرفوض", label_en: "Rejected" },
      { value: "ACTIVE", label_ar: "نشط", label_en: "Active" },
      { value: "WAITLISTED", label_ar: "قائمة انتظار", label_en: "Waitlisted" },
      { value: "WITHDRAWN", label_ar: "منسحب", label_en: "Withdrawn" },
    ];
    const lang = document.documentElement.getAttribute("lang") === "en" ? "en" : "ar";
    const labelKey = lang === "en" ? "label_en" : "label_ar";
    while (select.options.length > 1) select.remove(1);
    fallback.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s.value;
      opt.textContent = s[labelKey];
      select.appendChild(opt);
    });
  }

  // ===========================================================================
  // Preview
  // ===========================================================================
  async function loadReportPreview() {
    const period = getPeriod();
    if (!period.start || !period.end) {
      alert(reportsText("يرجى تحديد نطاق التاريخ", "Please select a date range"));
      return;
    }

    const reportType = getReportType();
    const payload = {
      report_type: reportType,
      period_start: period.start,
      period_end: period.end,
      filters: getFilters(),
    };

    destroyChartInstances();
    hideEl("dataQualityBanner");
    hideEl("previewInsights");
    hideEl("previewWarnings");
    setText("previewRecordCount", "...");
    setText("reportsLastUpdated", reportsText("جاري تحميل المعاينة...", "Loading preview..."));

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      const data = await res.json();
      renderPreview(data);
      setText("reportsLastUpdated", reportsText("تم تحديث المعاينة", "Preview updated"));
    } catch (e) {
      console.error("Preview failed", e);
      setText("reportsLastUpdated", reportsText("فشل تحميل المعاينة", "Preview failed"));
      getEl("previewTableBody").innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${reportsText("تعذر تحميل المعاينة.", "Failed to load preview.")}</td></tr>`;
    }
  }

  function renderPreview(data) {
    setText("previewRecordCount", `${data.total_records || 0} ${reportsText("سجل", "records")}`);

    // KPIs
    const kpiContainer = getEl("previewKpis");
    if (kpiContainer && data.kpis && data.kpis.length) {
      kpiContainer.innerHTML = data.kpis
        .map(
          (kpi) => `
            <div class="col-md-3 col-sm-6">
              <div class="p-3 bg-light rounded text-center border">
                <div class="fs-4 fw-bold text-primary mb-1">${escapeHtml(kpi.value.toString())} <small class="text-muted fs-6">${escapeHtml(kpi.unit)}</small></div>
                <div class="small text-muted">${escapeHtml(reportsText(kpi.label_ar || kpi.label, kpi.label_en || kpi.label))}</div>
              </div>
            </div>
            `
        )
        .join("");
    }

    // Charts (Structural Placeholder instead of misleading Dummy Data)
    const chartsContainer = getEl("previewCharts");
    if (chartsContainer && data.charts && data.charts.length) {
      chartsContainer.innerHTML = data.charts
        .map((chart) => {
          const isLarge = chart.type === 'line';
          let icon = "bi-bar-chart";
          if (chart.type === "line") icon = "bi-graph-up";
          if (chart.type === "pie" || chart.type === "doughnut") icon = "bi-pie-chart";
          
          return `
            <div class="${isLarge ? 'col-lg-12' : 'col-lg-6'}">
              <div class="border rounded p-4 text-center bg-light">
                <i class="bi ${icon} fs-1 text-muted opacity-50 mb-2 d-block"></i>
                <div class="fw-bold mb-1">${escapeHtml(reportsText(chart.label_ar || chart.label, chart.label_en || chart.label))}</div>
                <div class="small text-muted">${reportsText("الرسم البياني متاح في التصدير", "Chart available in export")}</div>
              </div>
            </div>
            `;
        })
        .join("");
    } else if (chartsContainer) {
      chartsContainer.innerHTML = `
        <div class="col-12 text-center text-muted py-4">
          <i class="bi bi-bar-chart fs-1"></i>
          <div class="small mt-2">${reportsText("ستظهر الرسوم البيانية هنا", "Charts will appear here")}</div>
        </div>
      `;
    }

    // Sample data table
    const thead = getEl("previewTableHead");
    const tbody = getEl("previewTableBody");
    if (thead && tbody && data.sample_data && data.sample_data.length) {
      const columns = Object.keys(data.sample_data[0]);
      thead.innerHTML = `<tr>${columns.map((c) => `<th>${escapeHtml(c)}</th>`).join("")}</tr>`;
      tbody.innerHTML = data.sample_data
        .map(
          (row) => `
        <tr>${columns
          .map((c) => {
            const val = row[c];
            if (c.toLowerCase().includes("date") || c.toLowerCase().includes("at")) {
              return `<td>${val ? new Date(val).toLocaleDateString() : "-"}</td>`;
            }
            return `<td>${escapeHtml(String(val ?? "-"))}</td>`;
          })
          .join("")}</tr>
      `
        )
        .join("");
    } else if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا توجد بيانات", "No data")}</td></tr>`;
    }

    // Insights
    if (data.insights && data.insights.length) {
      showEl("previewInsights");
      getEl("insightsList").innerHTML = data.insights
        .map((i) => {
          const text = typeof i === 'object' ? reportsText(i.ar || i, i.en || i) : i;
          return `<li class="list-group-item text-success border-success-subtle bg-success-subtle bg-opacity-10">${escapeHtml(text)}</li>`;
        })
        .join("");
    } else {
      hideEl("previewInsights");
    }

    // Warnings
    if (data.warnings && data.warnings.length) {
      showEl("previewWarnings");
      getEl("warningsList").innerHTML = data.warnings
        .map((w) => {
          const text = typeof w === 'object' ? reportsText(w.ar || w, w.en || w) : w;
          return `<li class="list-group-item text-warning border-warning-subtle bg-warning-subtle bg-opacity-10">${escapeHtml(text)}</li>`;
        })
        .join("");
    } else {
      hideEl("previewWarnings");
    }

    // Data quality
    if (data.data_quality) {
      showEl("dataQualityBanner");
      setText("dataQualityScore", data.data_quality.completeness_percent ?? 100);
    }
  }

  // ===========================================================================
  // Export
  // ===========================================================================
  async function exportCurrentReport() {
    const period = getPeriod();
    if (!period.start || !period.end) {
      alert(reportsText("يرجى تحديد نطاق التاريخ", "Please select a date range"));
      return;
    }

    const reportType = getReportType();
    const format = getEl("exportFormat")?.value || "CSV";
    const payload = {
      report_type: reportType,
      export_format: format,
      filters: {
        ...getFilters(),
        period_start: period.start,
        period_end: period.end,
      },
    };

    try {
      const res = await fetchWithAuth(`${API_BASE}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      const result = await res.json();
      if (result.job_id) {
        // Poll for completion
        pollExportStatus(result.job_id);
      }
    } catch (e) {
      console.error("Export failed", e);
      alert(reportsText("فشل بدء التصدير", "Export failed to start"));
    }
  }

  async function pollExportStatus(jobId) {
    const maxAttempts = 20;
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      try {
        const res = await fetchWithAuth(`${API_BASE}/export/${jobId}`);
        if (!res) return;
        const status = await res.json();
        if (status.status === "COMPLETED") {
          clearInterval(interval);
          window.location.href = `${API_BASE}/export/${jobId}/file`;
        } else if (status.status === "FAILED" || attempts >= maxAttempts) {
          clearInterval(interval);
          alert(reportsText("فشل التصدير أو تجاوز الوقت", "Export failed or timed out"));
        }
      } catch (e) {
        clearInterval(interval);
        console.error("Polling failed", e);
      }
    }, 1500);
  }

  // ===========================================================================
  // Templates
  // ===========================================================================
  async function saveAsTemplate() {
    const name = getEl("templateName")?.value?.trim();
    if (!name) {
      alert(reportsText("يرجى إدخال اسم القالب", "Please enter a template name"));
      return;
    }

    const payload = {
      name,
      report_type: getReportType(),
      filters: getFilters(),
      export_format: getEl("exportFormat")?.value || "CSV",
      include_charts: getEl("includeCharts")?.checked ?? true,
      include_summary: getEl("includeSummary")?.checked ?? true,
    };

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/templates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      await res.json();
      const modal = window.bootstrap?.Modal?.getInstance(getEl("saveTemplateModal"));
      if (modal) modal.hide();
      alert(reportsText("تم حفظ القالب بنجاح", "Template saved successfully"));
    } catch (e) {
      console.error("Save template failed", e);
      alert(reportsText("فشل حفظ القالب", "Failed to save template"));
    }
  }

  // ===========================================================================
  // Scheduling
  // ===========================================================================
  async function scheduleReport() {
    const name = getEl("scheduleName")?.value?.trim();
    if (!name) {
      alert(reportsText("يرجى إدخال اسم الجدولة", "Please enter a schedule name"));
      return;
    }

    const frequency = getEl("scheduleFrequency")?.value || "monthly";
    const recipientsRaw = getEl("scheduleRecipients")?.value || "";
    const recipients = recipientsRaw
      .split(",")
      .map((r) => r.trim())
      .filter((r) => r.length > 0);

    const payload = {
      name,
      report_type: getReportType(),
      filters: getFilters(),
      export_format: getEl("exportFormat")?.value || "CSV",
      frequency,
      recipients,
    };

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/schedules`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res) return;
      await res.json();
      const modal = window.bootstrap?.Modal?.getInstance(getEl("scheduleModal"));
      if (modal) modal.hide();
      alert(reportsText("تمت الجدولة بنجاح", "Report scheduled successfully"));
      loadRecentHistory();
    } catch (e) {
      console.error("Schedule failed", e);
      alert(reportsText("فشل جدولة التقرير", "Failed to schedule report"));
    }
  }

  // ===========================================================================
  // Recent History
  // ===========================================================================
  async function loadRecentHistory() {
    const tbody = getEl("reportsHistoryBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("جاري التحميل...", "Loading...")}</td></tr>`;

    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/history?limit=20`);
      if (!res) return;
      const data = await res.json();
      const items = Array.isArray(data) ? data : [];

      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا توجد تقارير سابقة", "No previous reports")}</td></tr>`;
        return;
      }

      const statusBadge = (status) => {
        const map = {
          PENDING: "bg-warning",
          PROCESSING: "bg-info",
          COMPLETED: "bg-success",
          FAILED: "bg-danger",
        };
        return map[status] || "bg-secondary";
      };

      tbody.innerHTML = items
        .map(
          (item) => `
        <tr>
          <td class="fw-medium">${escapeHtml(item.report_name || item.report_type)}</td>
          <td>${escapeHtml(item.format)}</td>
          <td>${item.generated_at ? new Date(item.generated_at).toLocaleString() : "-"}</td>
          <td><span class="badge ${statusBadge(item.status)}">${escapeHtml(item.status)}</span></td>
          <td class="text-center">
            ${item.status === "COMPLETED" && item.id ? `<a href="/api/analytics/export/${item.id}/file" class="btn btn-sm btn-outline-primary" title="{% if ui_lang == 'en' %}Download{% else %}تنزيل{% endif %}"><i class="bi bi-download"></i></a>` : ""}
            <button class="btn btn-sm btn-outline-secondary" data-action="rerun" data-id="${item.id}" title="{% if ui_lang == 'en' %}Regenerate{% else %}إعادة إنشاء{% endif %}"><i class="bi bi-arrow-clockwise"></i></button>
          </td>
        </tr>
      `
        )
        .join("");

      // Wire rerun buttons
      tbody.querySelectorAll("[data-action='rerun']").forEach((btn) => {
        btn.addEventListener("click", async () => {
          const id = btn.getAttribute("data-id");
          if (!id) return;
          try {
            await fetchWithAuth(`${API_BASE}/export/${id}/file`, { method: "GET" });
            window.location.href = `${API_BASE}/export/${id}/file`;
          } catch (e) {
            console.error("Rerun failed", e);
          }
        });
      });
    } catch (e) {
      console.error("History load failed", e);
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${reportsText("تعذر تحميل السجل", "Failed to load history")}</td></tr>`;
    }
  }

  // ===========================================================================
  // Stats
  // ===========================================================================
  async function loadSummaryStats() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/history?limit=100`);
      if (!res) return;
      const data = await res.json();
      const items = Array.isArray(data) ? data : [];
      const now = new Date();
      const thisMonth = items.filter((it) => {
        const d = new Date(it.generated_at);
        return d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear();
      });
      const failed = items.filter((it) => it.status === "FAILED");

      setText("statReportsGenerated", String(thisMonth.length));
      setText("statFailedExports", String(failed.length));
      if (items.length) {
        setText("statLastGenerated", new Date(items[0].generated_at).toLocaleDateString());
        setText("statLastGeneratedTime", new Date(items[0].generated_at).toLocaleTimeString());
      }
    } catch (e) {
      console.error("Stats load failed", e);
    }
  }

  async function loadScheduledCount() {
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/schedules`);
      if (!res) return;
      const data = await res.json();
      const active = Array.isArray(data) ? data.filter((s) => s.is_active) : [];
      setText("statScheduledReports", String(active.length));
    } catch (e) {
      console.error("Schedules load failed", e);
    }
  }

  // ===========================================================================
  // Init
  // ===========================================================================
  async function init() {
    await loadGovernorates();
    await loadKindergartens();
    await loadStatuses();
    await loadReviewers();
    await loadSummaryStats();
    await loadScheduledCount();
    await loadRecentHistory();

    // Wire events
    getEl("previewReportBtn")?.addEventListener("click", loadReportPreview);
    getEl("exportReportBtn")?.addEventListener("click", exportCurrentReport);
    getEl("saveTemplateBtn")?.addEventListener("click", () => {
      getEl("templateName")?.focus();
      const modal = new window.bootstrap.Modal(getEl("saveTemplateModal"));
      modal.show();
    });
    getEl("confirmSaveTemplate")?.addEventListener("click", saveAsTemplate);
    getEl("scheduleReportBtn")?.addEventListener("click", () => {
      getEl("scheduleName")?.focus();
      const modal = new window.bootstrap.Modal(getEl("scheduleModal"));
      modal.show();
    });
    getEl("confirmSchedule")?.addEventListener("click", scheduleReport);
    getEl("refreshHistoryBtn")?.addEventListener("click", () => {
      loadRecentHistory();
      loadSummaryStats();
      loadScheduledCount();
    });
    getEl("resetFiltersBtn")?.addEventListener("click", () => {
      setTimeout(() => {
        loadRecentHistory();
        loadSummaryStats();
        loadScheduledCount();
      }, 100);
    });

    // Governorate -> kindergarten cascade
    getEl("governorateFilter")?.addEventListener("change", loadKindergartens);

    // Tab change -> update hidden reportType and refresh preview
    document.querySelectorAll("#reportCategoryTabs .nav-link").forEach((tab) => {
      tab.addEventListener("shown.bs.tab", () => {
        getEl("reportType").value = getReportType();
        // Update visible filters based on report type
        updateFilterVisibility();
        loadReportPreview();
      });
    });

    // Period change
    getEl("periodStart")?.addEventListener("change", loadReportPreview);
    getEl("periodEnd")?.addEventListener("change", loadReportPreview);

    // Auto-load initial preview
    loadReportPreview();
  }

  function updateFilterVisibility() {
    const type = getReportType();
    const showStatus = ["enrollment", "full_audit"].includes(type);
    const showSeverity = type === "incidents";
    const showSource = type === "enrollment";
    const showReviewer = type === "enrollment";

    toggleFilterVisibility("statusFilter", showStatus);
    toggleFilterVisibility("severityFilter", showSeverity);
    toggleFilterVisibility("sourceFilter", showSource);
    toggleFilterVisibility("reviewerFilter", showReviewer);
  }

  function toggleFilterVisibility(id, visible) {
    const el = getEl(id);
    if (!el) return;
    const wrapper = el.closest(".mb-3");
    if (wrapper) {
      wrapper.style.display = visible ? "" : "none";
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
