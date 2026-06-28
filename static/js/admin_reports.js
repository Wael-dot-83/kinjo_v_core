// admin_reports.js — Enterprise Reports Center logic
// Requires: Chart.js, chart_utils.js, sanitize.js, admin_analytics.js loaded beforehand.

(function () {
  "use strict";

  if (window.AdminReports) return;
  window.AdminReports = {};

  const API_BASE = "/api/analytics";

  let historyItems = [];
  let previewItems = [];
  let previewColumns = [];
  let previewCurrentPage = 1;
  const previewPageSize = 5;
  let previewSortColumn = "";
  let previewSortDirection = "asc";
  let historySearchText = "";
  let historyCurrentPage = 1;
  const historyPageSize = 5;

  function showToast(msg) {
    const toastMessage = getEl("toastMessage");
    const actionToast = getEl("actionToast");
    if (toastMessage && actionToast) {
        toastMessage.innerText = msg;
        const toast = new window.bootstrap.Toast(actionToast);
        toast.show();
    }
  }

  function updateFilterVisibility(reportType) {
    const gov = getEl("filterGovContainer");
    const kg = getEl("filterKgContainer");
    const status = getEl("filterStatusContainer");
    const severity = getEl("filterSeverityContainer");
    const source = getEl("filterSourceContainer");
    const reviewer = getEl("filterReviewerContainer");

    // Hide all first
    [gov, kg, status, severity, source, reviewer].forEach(el => {
      if (el) el.classList.add("d-none");
    });

    if (reportType === "attendance" || reportType === "compliance") {
      if (gov) gov.classList.remove("d-none");
      if (kg) kg.classList.remove("d-none");
    } else if (reportType === "incidents") {
      if (gov) gov.classList.remove("d-none");
      if (kg) kg.classList.remove("d-none");
      if (status) status.classList.remove("d-none");
      if (severity) severity.classList.remove("d-none");
    } else if (reportType === "enrollment") {
      if (status) status.classList.remove("d-none");
      if (source) source.classList.remove("d-none");
      if (reviewer) reviewer.classList.remove("d-none");
    } else if (reportType === "full_audit") {
      // only uses date filters which are outside the dynamic filters section
    }
  }


  // ===========================================================================
  // Helpers
  // ===========================================================================
    function getMultiSelectValues(id) {
    const el = getEl(id);
    if (!el) return [];
    return Array.from(el.selectedOptions).map(opt => opt.value).filter(val => val !== "");
  }

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
      governorates: getMultiSelectValues("governorateFilter"),
      kindergarten_ids: getMultiSelectValues("kindergartenFilter").map(Number),
      statuses: getMultiSelectValues("statusFilter"),
      severities: getMultiSelectValues("severityFilter"),
      sources: getMultiSelectValues("sourceFilter"),
      reviewer_ids: getMultiSelectValues("reviewerFilter").map(Number),
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
    if (!window.Chart) return;
    Object.values(window.Chart.instances).forEach(chart => {
      if (chart.canvas && chart.canvas.id.startsWith("chart-")) {
        chart.destroy();
      }
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

    // Charts 
    const chartsContainer = getEl("previewCharts");
    if (chartsContainer && data.charts && data.charts.length) {
      chartsContainer.innerHTML = data.charts
        .map((chart) => {
          const isLarge = chart.type === 'line' || chart.type === 'bar';
          return `
            <div class="${isLarge ? 'col-lg-12' : 'col-lg-6'} mb-4">
              <div class="border rounded p-3 bg-white shadow-sm h-100">
                <div class="fw-bold mb-3 text-center">${escapeHtml(reportsText(chart.label_ar || chart.label, chart.label_en || chart.label))}</div>
                <div style="position: relative; height: 300px; width: 100%;">
                  <canvas id="chart-${chart.id}"></canvas>
                </div>
              </div>
            </div>
            `;
        })
        .join("");
        
      data.charts.forEach(chart => {
        const canvas = document.getElementById(`chart-${chart.id}`);
        if (!canvas) return;
        const chartData = chart.data || { labels: [], datasets: [] };
        
        // Handle bilingual labels
        if (chartData.labels) {
            chartData.labels = chartData.labels.map(l => typeof l === 'object' && l !== null ? reportsText(l.ar || l.en, l.en || l.ar) : l);
        }
        if (chartData.datasets) {
            chartData.datasets.forEach(ds => {
                if (typeof ds.label === 'object' && ds.label !== null) {
                    ds.label = reportsText(ds.label.ar || ds.label.en, ds.label.en || ds.label.ar);
                }
            });
        }
        
        new window.Chart(canvas, {
          type: chart.type || 'bar',
          data: chartData,
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: 'bottom',
                rtl: document.documentElement.getAttribute("dir") === "rtl" || document.documentElement.getAttribute("lang") === "ar",
                textDirection: document.documentElement.getAttribute("dir") === "rtl" || document.documentElement.getAttribute("lang") === "ar" ? 'rtl' : 'ltr'
              },
              tooltip: {
                rtl: document.documentElement.getAttribute("dir") === "rtl" || document.documentElement.getAttribute("lang") === "ar",
                textDirection: document.documentElement.getAttribute("dir") === "rtl" || document.documentElement.getAttribute("lang") === "ar" ? 'rtl' : 'ltr'
              }
            }
          }
        });
      });
    } else if (chartsContainer) {
      chartsContainer.innerHTML = `
        <div class="col-12 text-center text-muted py-4">
          <i class="bi bi-bar-chart fs-1"></i>
          <div class="small mt-2">${reportsText("ستظهر الرسوم البيانية هنا", "Charts will appear here")}</div>
        </div>
      `;
    }

    // Sample data table
    previewItems = data.sample_data || [];
    previewColumns = previewItems.length ? Object.keys(previewItems[0]) : [];
    previewCurrentPage = 1;
    previewSortColumn = "";
    
    renderPreviewTable();
  }

  function renderPreviewTable() {
    const thead = getEl("previewTableHead");
    const tbody = getEl("previewTableBody");
    const pag = getEl("previewTablePagination");

    if (!thead || !tbody) return;

    if (!previewItems.length) {
      thead.innerHTML = `<tr><th colspan="5" class="text-center text-muted">${reportsText("لا تتوفر معاينة للتقرير", "No preview data")}</th></tr>`;
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا توجد بيانات", "No data")}</td></tr>`;
      if (pag) pag.classList.add("d-none");
      return;
    }

    if (pag) pag.classList.remove("d-none");

    // Sort
    let sorted = [...previewItems];
    if (previewSortColumn) {
      sorted.sort((a, b) => {
        let valA = a[previewSortColumn];
        let valB = b[previewSortColumn];
        if (valA === null || valA === undefined) valA = "";
        if (valB === null || valB === undefined) valB = "";
        if (typeof valA === 'string') valA = valA.toLowerCase();
        if (typeof valB === 'string') valB = valB.toLowerCase();
        if (valA < valB) return previewSortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return previewSortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }

    // Paginate
    const totalPages = Math.ceil(sorted.length / previewPageSize);
    if (previewCurrentPage > totalPages) previewCurrentPage = totalPages;
    if (previewCurrentPage < 1) previewCurrentPage = 1;

    const startIdx = (previewCurrentPage - 1) * previewPageSize;
    const endIdx = Math.min(startIdx + previewPageSize, sorted.length);
    const paginated = sorted.slice(startIdx, endIdx);

    // Render Headers with sort icons
    thead.innerHTML = `<tr>${previewColumns.map((col) => {
      const isSorted = previewSortColumn === col;
      const caret = isSorted ? (previewSortDirection === 'asc' ? ' <i class="bi bi-caret-up-fill"></i>' : ' <i class="bi bi-caret-down-fill"></i>') : '';
      return `<th style="cursor: pointer" class="sortable-header" data-col="${escapeHtml(col)}">${escapeHtml(col)}${caret}</th>`;
    }).join("")}</tr>`;

    // Add sort listeners
    thead.querySelectorAll('.sortable-header').forEach(th => {
      th.addEventListener('click', (e) => {
        const col = e.currentTarget.getAttribute('data-col');
        if (previewSortColumn === col) {
          previewSortDirection = previewSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
          previewSortColumn = col;
          previewSortDirection = 'asc';
        }
        renderPreviewTable();
      });
    });

    // Render Rows
    tbody.innerHTML = paginated
      .map(
        (row) => `
      <tr>${previewColumns
        .map((col) => {
          let val = row[col];
          if (val === null || val === undefined) val = "-";
          // Try to format if it looks like ISO date
          if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}/.test(val)) {
             val = formatLocalDate(val);
          }
          return `<td>${escapeHtml(String(val))}</td>`;
        })
        .join("")}</tr>`
      )
      .join("");

    // Update pagination controls
    setText("previewPaginationInfo", `${startIdx + 1}-${endIdx} of ${sorted.length}`);
    const prevBtn = getEl("prevPreviewPageBtn");
    const nextBtn = getEl("nextPreviewPageBtn");
    if (prevBtn) prevBtn.disabled = previewCurrentPage === 1;
    if (nextBtn) nextBtn.disabled = previewCurrentPage === totalPages;
  }

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
  
  // ===========================================================================
  // Templates Loading logic
  // ===========================================================================
  let loadedTemplates = [];

  async function loadSavedTemplates() {
    const list = getEl("templateList");
    if (!list) return;
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/templates`);
      if (!res) return;
      loadedTemplates = await res.json();
      
      if (!loadedTemplates.length) {
        list.innerHTML = `<li><span class="dropdown-item-text text-muted small">${reportsText("لا توجد قوالب محفوظة", "No saved templates")}</span></li>`;
        return;
      }
      
      list.innerHTML = loadedTemplates.map(t => {
          return `<li><a class="dropdown-item" href="#" data-template-id="${t.id}">${escapeHtml(t.name)}</a></li>`;
      }).join('');
      
      list.querySelectorAll('.dropdown-item').forEach(item => {
          item.addEventListener('click', (e) => {
              e.preventDefault();
              const tid = e.target.getAttribute('data-template-id');
              applyTemplate(tid);
          });
      });
    } catch (e) {
      console.error("Failed to load templates", e);
      list.innerHTML = `<li><span class="dropdown-item-text text-danger small">${reportsText("تعذر التحميل", "Failed to load")}</span></li>`;
    }
  }

  function applyTemplate(id) {
      const t = loadedTemplates.find(x => String(x.id) === String(id));
      if (!t) return;
      
      // switch tab
      const tabMap = {
          "attendance": "#tab-attendance",
          "incidents": "#tab-incidents",
          "compliance": "#tab-compliance",
          "enrollment": "#tab-enrollment",
          "full_audit": "#tab-audit"
      };
      const tabId = tabMap[t.report_type];
      if (tabId) {
          const tabEl = document.querySelector(tabId);
          if (tabEl) {
              const tab = new window.bootstrap.Tab(tabEl);
              tab.show();
          }
      }
      
      // Wait a moment for tab switch to update visibility
      setTimeout(() => {
          if (t.filters) {
              const setMultiValues = (id, vals) => {
                  const select = getEl(id);
                  if (!select || !vals) return;
                  const arr = Array.isArray(vals) ? vals : [vals];
                  Array.from(select.options).forEach(opt => {
                      opt.selected = arr.map(String).includes(String(opt.value));
                  });
              };
              setMultiValues("governorateFilter", t.filters.governorates || t.filters.governorate);
              setMultiValues("kindergartenFilter", t.filters.kindergarten_ids || t.filters.kindergarten_id);
              setMultiValues("statusFilter", t.filters.statuses || t.filters.status);
              setMultiValues("severityFilter", t.filters.severities || t.filters.severity);
              setMultiValues("sourceFilter", t.filters.sources || t.filters.source);
              setMultiValues("reviewerFilter", t.filters.reviewer_ids || t.filters.reviewer_id);
          }
          if(getEl("exportFormat")) getEl("exportFormat").value = t.export_format || "CSV";
          if(getEl("includeCharts")) getEl("includeCharts").checked = t.include_charts;
          if(getEl("includeSummary")) getEl("includeSummary").checked = t.include_summary;
          
          loadReportPreview();
      }, 100);
  }

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
      showToast(reportsText("تم حفظ القالب بنجاح", "Template saved successfully"));
      loadSavedTemplates();
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
      const res = await fetchWithAuth(`${API_BASE}/reports/history?limit=100`);
      if (!res) return;
      const data = await res.json();
      historyItems = Array.isArray(data) ? data : [];
      historyCurrentPage = 1;
      renderRecentHistory();
    } catch (e) {
      console.error("History load failed", e);
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${reportsText("تعذر تحميل السجل", "Failed to load history")}</td></tr>`;
    }
  }

  function renderRecentHistory() {
    const tbody = getEl("reportsHistoryBody");
    if (!tbody) return;

    // Filter
    const filtered = historyItems.filter(item => {
      const name = (item.report_name || item.report_type).toLowerCase();
      const format = (item.format || "").toLowerCase();
      const status = (item.status || "").toLowerCase();
      const query = historySearchText.toLowerCase();
      return name.includes(query) || format.includes(query) || status.includes(query);
    });

    if (!filtered.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-muted">${reportsText("لا توجد نتائج مطابقة", "No matching reports")}</td></tr>`;
      setText("historyPaginationInfo", "0-0 of 0");
      return;
    }

    const totalPages = Math.ceil(filtered.length / historyPageSize);
    if (historyCurrentPage > totalPages) historyCurrentPage = totalPages;
    if (historyCurrentPage < 1) historyCurrentPage = 1;

    const startIdx = (historyCurrentPage - 1) * historyPageSize;
    const endIdx = Math.min(startIdx + historyPageSize, filtered.length);
    const paginated = filtered.slice(startIdx, endIdx);

    const statusBadge = (status) => {
      const map = {
        PENDING: "bg-warning",
        PROCESSING: "bg-info",
        COMPLETED: "bg-success",
        FAILED: "bg-danger",
      };
      return map[status] || "bg-secondary";
    };

    tbody.innerHTML = paginated
      .map(
        (item) => `
      <tr>
        <td class="fw-medium">${escapeHtml(item.report_name || item.report_type)}</td>
        <td>${escapeHtml(item.format)}</td>
        <td>${item.generated_at ? new Date(item.generated_at).toLocaleString() : "-"}</td>
        <td><span class="badge ${statusBadge(item.status)}">${escapeHtml(item.status)}</span></td>
        <td class="text-center">
          ${item.status === "COMPLETED" && item.id ? `<a href="/api/analytics/export/${item.id}/file" class="btn btn-sm btn-outline-primary" aria-label="Download report"><i class="bi bi-download"></i></a>` : ""}
          ${item.status === "FAILED" ? `<button class="btn btn-sm btn-outline-danger retry-export-btn" data-job-id="${item.id}" aria-label="Retry export"><i class="bi bi-arrow-counterclockwise"></i></button>` : ""}
        </td>
      </tr>`
      )
      .join("");

    // Wire up retry buttons
    tbody.querySelectorAll('.retry-export-btn').forEach(btn => {
      btn.addEventListener('click', async (e) => {
         const jobId = e.currentTarget.getAttribute('data-job-id');
         await retryExportJob(jobId);
      });
    });

    // Update pagination elements
    setText("historyPaginationInfo", `${startIdx + 1}-${endIdx} of ${filtered.length}`);
    const prevBtn = getEl("prevHistoryPageBtn");
    const nextBtn = getEl("nextHistoryPageBtn");
    if (prevBtn) prevBtn.disabled = historyCurrentPage === 1;
    if (nextBtn) nextBtn.disabled = historyCurrentPage === totalPages;
  }

  async function retryExportJob(jobId) {
     showToast(reportsText("جاري إعادة محاولة التصدير...", "Retrying export..."));
     try {
       const res = await fetchWithAuth(`${API_BASE}/export`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ retry_job_id: Number(jobId) })
       });
       if (res) {
          showToast(reportsText("تم بدء تصدير التقرير", "Export job started"));
          await loadRecentHistory();
       }
     } catch(e) {
        showToast(reportsText("تعذر إعادة محاولة التصدير", "Failed to retry export"));
     }
  }

  
  async function loadSavedTemplates() {
    const list = getEl("templateList");
    if (!list) return;
    try {
      const res = await fetchWithAuth(`${API_BASE}/reports/templates`);
      if (!res) return;
      loadedTemplates = await res.json();
      
      if (!loadedTemplates.length) {
        list.innerHTML = `<li><span class="dropdown-item-text text-muted small">${reportsText("لا توجد قوالب محفوظة", "No saved templates")}</span></li>`;
        return;
      }
      
      list.innerHTML = loadedTemplates.map(t => {
          return `<li><a class="dropdown-item" href="#" data-template-id="${t.id}">${escapeHtml(t.name)}</a></li>`;
      }).join('');
      
      list.querySelectorAll('.dropdown-item').forEach(item => {
          item.addEventListener('click', (e) => {
              e.preventDefault();
              const tid = e.target.getAttribute('data-template-id');
              applyTemplate(tid);
          });
      });
    } catch (e) {
      console.error("Failed to load templates", e);
      list.innerHTML = `<li><span class="dropdown-item-text text-danger small">${reportsText("تعذر التحميل", "Failed to load")}</span></li>`;
    }
  }

  function applyTemplate(id) {
      const t = loadedTemplates.find(x => String(x.id) === String(id));
      if (!t) return;
      
      // switch tab
      const tabMap = {
          "attendance": "#tab-attendance",
          "incidents": "#tab-incidents",
          "compliance": "#tab-compliance",
          "enrollment": "#tab-enrollment",
          "full_audit": "#tab-audit"
      };
      const tabId = tabMap[t.report_type];
      if (tabId) {
          const tabEl = document.querySelector(tabId);
          if (tabEl) {
              const tab = new window.bootstrap.Tab(tabEl);
              tab.show();
          }
      }
      
      // Wait a moment for tab switch to update visibility
      setTimeout(() => {
          if (t.filters) {
              const setMultiValues = (id, vals) => {
                  const select = getEl(id);
                  if (!select || !vals) return;
                  const arr = Array.isArray(vals) ? vals : [vals];
                  Array.from(select.options).forEach(opt => {
                      opt.selected = arr.map(String).includes(String(opt.value));
                  });
              };
              setMultiValues("governorateFilter", t.filters.governorates || t.filters.governorate);
              setMultiValues("kindergartenFilter", t.filters.kindergarten_ids || t.filters.kindergarten_id);
              setMultiValues("statusFilter", t.filters.statuses || t.filters.status);
              setMultiValues("severityFilter", t.filters.severities || t.filters.severity);
              setMultiValues("sourceFilter", t.filters.sources || t.filters.source);
              setMultiValues("reviewerFilter", t.filters.reviewer_ids || t.filters.reviewer_id);
          }
          if(getEl("exportFormat")) getEl("exportFormat").value = t.export_format || "CSV";
          if(getEl("includeCharts")) getEl("includeCharts").checked = t.include_charts;
          if(getEl("includeSummary")) getEl("includeSummary").checked = t.include_summary;
          
          loadReportPreview();
      }, 100);
  }

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
      showToast(reportsText("تم حفظ القالب بنجاح", "Template saved successfully"));
      loadSavedTemplates();
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
    await loadSavedTemplates();

    // Wire events
    const initialType = getReportType();
    updateFilterVisibility(initialType);

    document.querySelectorAll("#reportCategoryTabs .nav-link").forEach(tab => {
        tab.addEventListener("shown.bs.tab", (e) => {
            const reportType = getReportType();
            updateFilterVisibility(reportType);
        });
    });

    // History search input
    getEl("searchHistoryInput")?.addEventListener("input", (e) => {
        historySearchText = e.target.value;
        historyCurrentPage = 1;
        renderRecentHistory();
    });

    // History Pagination controls
    getEl("prevHistoryPageBtn")?.addEventListener("click", () => {
        if (historyCurrentPage > 1) {
            historyCurrentPage--;
            renderRecentHistory();
        }
    });

    getEl("nextHistoryPageBtn")?.addEventListener("click", () => {
        const totalPages = Math.ceil(historyItems.length / historyPageSize);
        if (historyCurrentPage < totalPages) {
            historyCurrentPage++;
            renderRecentHistory();
        }
    });

    // Preview Pagination controls
    getEl("prevPreviewPageBtn")?.addEventListener("click", () => {
        if (previewCurrentPage > 1) {
            previewCurrentPage--;
            renderPreviewTable();
        }
    });

    getEl("nextPreviewPageBtn")?.addEventListener("click", () => {
        const totalPages = Math.ceil(previewItems.length / previewPageSize);
        if (previewCurrentPage < totalPages) {
            previewCurrentPage++;
            renderPreviewTable();
        }
    });

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
