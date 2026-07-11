(function () {
  "use strict";
  const page = document.querySelector("[data-agency-reports-page]");
  if (!page) return;
  const lang = document.documentElement.lang === "en" ? "en" : "ar";
  const root = document.getElementById("agency-reports-root") || document.getElementById("agency-report-root");
  const api = (path) => fetch(path, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } }).then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  const t = (ar, en) => lang === "en" ? en : ar;

  const agencyLogoFiles = {
    moe: "moe.jpg",
    moh: "moh.jpg",
    dos: "gsd.jpg",
    ncfa: "ncfa.png",
    mol: "mol.png",
    mosd: "mosd.jpg"
  };

  function clear(el) { if (el) el.innerHTML = ""; }

  function pill(text, kind, icon) {
    const span = document.createElement("span");
    span.className = "agency-status agency-status--" + (kind || "default");
    if (icon) {
      const i = document.createElement("i");
      i.className = "bi " + icon;
      i.setAttribute("aria-hidden", "true");
      span.appendChild(i);
      span.appendChild(document.createTextNode(" " + text));
    } else {
      span.textContent = text;
    }
    return span;
  }

  function statusBadge(status) {
    if (status === "ready") return pill(t("جاهزة", "Ready"), "success", "bi-check-circle-fill");
    if (status === "requires_structured_data") return pill(t("تحتاج بيانات", "Needs data"), "warning", "bi-exclamation-triangle-fill");
    return pill(t("غير متاح", "Unavailable"), "default", "bi-dash-circle");
  }

  function logoBadge(agency) {
    const badge = document.createElement("span");
    badge.className = "agency-logo-badge";
    badge.setAttribute("aria-hidden", "true");
    if (agency.icon) {
      const i = document.createElement("i");
      i.className = "bi " + agency.icon;
      badge.appendChild(i);
    } else {
      const name = (lang === "en" ? agency.name_en : agency.name_ar) || agency.code || "";
      badge.textContent = name.trim().slice(0, 2);
      badge.classList.add("agency-logo-badge--text");
    }
    return badge;
  }

  window.renderAgencyLogo = function renderAgencyLogo(agency, size) {
    const logoFile = agencyLogoFiles[agency.code];
    if (logoFile) {
      const img = document.createElement("img");
      img.className = "agency-card-logo";
      img.src = "/static/img/agencies/" + logoFile;
      img.alt = "";
      img.setAttribute("aria-hidden", "true");
      if (size) { img.width = size; img.height = size; }
      return img;
    }
    return logoBadge(agency);
  };

  function renderSummaryWidgets(agencies) {
    const box = document.getElementById("agency-summary-widgets");
    if (!box) return;
    const total = agencies.length;
    const totalReports = agencies.reduce((s, a) => s + (a.report_count || 0), 0);
    const readyReports = agencies.reduce((s, a) => s + (a.ready_report_count || 0), 0);
    const needsData = agencies.reduce((s, a) => s + (a.requires_data_count || 0), 0);
    const items = [
      { label: t("عدد الجهات الرسمية", "Official Agencies"), value: total, icon: "bi-building" },
      { label: t("إجمالي التقارير", "Total Reports"), value: totalReports, icon: "bi-file-earmark-bar-graph" },
      { label: t("التقارير الجاهزة", "Ready Reports"), value: readyReports, icon: "bi-check-circle-fill", cls: "agency-widget--success" },
      { label: t("تحتاج بيانات منظمة", "Need structured data"), value: needsData, icon: "bi-exclamation-triangle-fill", cls: "agency-widget--warning" },
    ];
    box.innerHTML = "";
    const grid = document.createElement("div");
    grid.className = "agency-summary-widgets-grid";
    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "agency-summary-widget" + (item.cls ? " " + item.cls : "");
      const ico = document.createElement("i");
      ico.className = "bi " + item.icon + " agency-widget-icon";
      ico.setAttribute("aria-hidden", "true");
      const val = document.createElement("strong");
      val.className = "agency-widget-value";
      val.textContent = item.value;
      const lbl = document.createElement("span");
      lbl.className = "agency-widget-label";
      lbl.textContent = item.label;
      card.append(ico, val, lbl);
      grid.appendChild(card);
    });
    box.appendChild(grid);
  }

  function renderIndex(data) {
    clear(root);
    renderSummaryWidgets(data.agencies || []);

    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");

    data.agencies.forEach((agency) => {
      const li = document.createElement("li");
      li.className = "agency-card";

      // Header: logo + name
      const header = document.createElement("div");
      header.className = "agency-card__head";
      header.appendChild(window.renderAgencyLogo(agency, 72));
      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? agency.name_en : agency.name_ar;
      header.appendChild(h2);

      // Description
      const desc = document.createElement("p");
      desc.className = "agency-card-desc";
      desc.textContent = agency.description_ar || "";

      // Metadata row
      const meta = document.createElement("div");
      meta.className = "agency-card-meta";
      meta.append(
        pill(t("التقارير: ", "Reports: ") + (agency.report_count || 0), "info", "bi-file-earmark"),
        pill(t("جاهزة: ", "Ready: ") + (agency.ready_report_count || 0), "success", "bi-check-circle")
      );
      if (agency.requires_data_count) {
        meta.append(pill(t("تحتاج بيانات: ", "Needs data: ") + agency.requires_data_count, "warning", "bi-exclamation-triangle"));
      }

      // Open button
      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary agency-card-btn";
      link.href = "/admin/agency-reports/" + encodeURIComponent(agency.code);
      link.textContent = t("فتح تقارير الجهة", "Open Agency Reports");
      link.setAttribute("aria-label", t("فتح تقارير " + (agency.name_ar || agency.code), "Open reports for " + (agency.name_en || agency.code)));

      li.append(header, desc, meta, link);

      li.addEventListener("click", function (e) {
        e.stopPropagation();
        window.location.href = "/admin/agency-reports/" + encodeURIComponent(agency.code);
      });
      link.addEventListener("click", function (e) { e.stopPropagation(); });

      list.appendChild(li);
    });

    if (!data.agencies.length) {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد تقارير جاهزة حالياً. يرجى استكمال البيانات المطلوبة أو مراجعة إعدادات التكامل.", "No reports are available at this time. Please complete the required data or review integration settings.");
      root.appendChild(empty);
    } else {
      root.appendChild(list);
    }
  }

  function renderAgency(data) {
    clear(root);

    // Update breadcrumb and page title
    const breadcrumbName = document.getElementById("agency-current-name");
    if (breadcrumbName) breadcrumbName.textContent = lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const titleEl = document.getElementById("agency-reports-title");
    if (titleEl) titleEl.textContent = lang === "en" ? data.agency_name_en : data.agency_name_ar;
    const desc = document.getElementById("agency-description");
    if (desc) desc.textContent = data.description_ar || "";

    // Render agency logo in header
    const logoContainer = document.getElementById("agency-logo-container");
    if (logoContainer && window.renderAgencyLogo) {
      const agencyObj = { code: data.agency_code, name_ar: data.agency_name_ar, name_en: data.agency_name_en, icon: data.icon };
      logoContainer.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Agency explanation
    if (data.description_ar) {
      const expl = document.createElement("div");
      expl.className = "agency-alert agency-alert--info";
      expl.textContent = data.description_ar;
      root.appendChild(expl);
    }

    // Report cards
    const list = document.createElement("ul");
    list.className = "agency-card-grid";
    list.setAttribute("role", "list");

    data.reports.forEach((report) => {
      const li = document.createElement("li");
      li.className = "agency-card agency-report-card";

      const h2 = document.createElement("h2");
      h2.textContent = lang === "en" ? report.title_en : report.title_ar;

      const reportDesc = document.createElement("p");
      reportDesc.className = "agency-card-desc";
      reportDesc.textContent = report.description_ar || "";

      const statusRow = document.createElement("div");
      statusRow.className = "agency-card-meta";
      statusRow.appendChild(statusBadge(report.status));
      if (report.status !== "ready" && report.reason_ar) {
        const reason = document.createElement("span");
        reason.className = "agency-card-reason";
        reason.textContent = report.reason_ar;
        statusRow.appendChild(reason);
      }

      const link = document.createElement("a");
      link.className = "admin-btn admin-btn-primary agency-card-btn" + (report.status !== "ready" ? " disabled" : "");
      link.href = "/admin/agency-reports/" + encodeURIComponent(data.agency_code) + "/" + encodeURIComponent(report.report_code);
      link.textContent = t("فتح التقرير", "Open Report");
      if (report.status !== "ready") {
        link.setAttribute("aria-disabled", "true");
        link.setAttribute("tabindex", "-1");
      }

      li.append(h2, reportDesc, statusRow, link);
      list.appendChild(li);
    });

    if (!data.reports.length) {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد تقارير جاهزة حالياً. يرجى استكمال البيانات المطلوبة أو مراجعة إعدادات التكامل.", "No reports available currently. Please complete required data or review integration settings.");
      root.appendChild(empty);
    } else {
      root.appendChild(list);
    }
  }

  function renderReport(payload) {
    clear(root);

    // Populate breadcrumbs and header
    const titleEl = document.getElementById("agency-report-title");
    if (titleEl) titleEl.textContent = lang === "en" ? payload.metadata.report_title_en : payload.metadata.report_title_ar;
    const descEl = document.getElementById("agency-report-description");
    if (descEl) descEl.textContent = payload.metadata.description_ar || "";
    const breadcrumbAgency = document.getElementById("breadcrumb-agency-name");
    if (breadcrumbAgency) {
      breadcrumbAgency.textContent = payload.metadata.agency_name_ar || payload.metadata.agency_code;
      breadcrumbAgency.href = "/admin/agency-reports/" + encodeURIComponent(payload.metadata.agency_code);
    }
    const breadcrumbReport = document.getElementById("breadcrumb-report-name");
    if (breadcrumbReport) breadcrumbReport.textContent = payload.metadata.report_title_ar || payload.metadata.report_code;

    // Agency logo in report header
    const logoEl = document.getElementById("report-agency-logo");
    if (logoEl && window.renderAgencyLogo) {
      const agencyObj = { code: payload.metadata.agency_code, name_ar: payload.metadata.agency_name_ar };
      logoEl.appendChild(window.renderAgencyLogo(agencyObj, 72));
    }

    // Executive summary
    const summary = document.createElement("section");
    summary.className = "agency-report-summary";
    summary.setAttribute("aria-labelledby", "agency-summary-title");
    const sumH2 = document.createElement("h2");
    sumH2.id = "agency-summary-title";
    sumH2.textContent = t("ملخص النتائج", "Results Summary");
    const dl = document.createElement("dl");
    const summaryLabels = payload.summary_labels || {};
    Object.entries(payload.summary || {}).forEach(([key, value]) => {
      if (key === "message_ar") return;
      const dt = document.createElement("dt"); dt.textContent = summaryLabels[key] || key;
      const dd = document.createElement("dd"); dd.textContent = value == null ? "—" : String(value);
      dl.append(dt, dd);
    });
    summary.append(sumH2, dl);
    root.appendChild(summary);

    if (payload.unavailable_indicators && payload.unavailable_indicators.length) {
      const alert = document.createElement("div");
      alert.className = "agency-alert agency-alert--warning";
      alert.textContent = payload.summary.message_ar || t("هذا التقرير يتطلب بيانات منظمة إضافية.", "This report requires additional structured data.");
      root.appendChild(alert);
      return;
    }

    // Chart placeholder (if chart data provided)
    if (payload.chart) {
      const chartSection = document.createElement("div");
      chartSection.className = "agency-chart-section";
      const chartTitle = document.createElement("h2");
      chartTitle.className = "agency-chart-title";
      chartTitle.textContent = payload.chart.title_ar || t("الرسم البياني", "Chart");
      chartSection.appendChild(chartTitle);
      if (window.Chart && payload.chart.series && payload.chart.series.length) {
        const canvas = document.createElement("canvas");
        canvas.id = "agency-report-chart";
        canvas.setAttribute("aria-label", payload.chart.title_ar || "");
        canvas.setAttribute("role", "img");
        chartSection.appendChild(canvas);
        const chartInst = new window.Chart(canvas.getContext("2d"), {
          type: payload.chart.type === "pie" ? "pie" : "bar",
          data: {
            labels: payload.chart.series.map((s) => s.label),
            datasets: [{ label: payload.chart.title_ar || "", data: payload.chart.series.map((s) => s.value), backgroundColor: ["#1f6f54","#2f8f6d","#2b6cb0","#6b46c1","#c0392b","#e0a90e","#718096"] }]
          },
          options: { responsive: true, plugins: { legend: { position: payload.chart.type === "pie" ? "bottom" : "top" } } }
        });
        // Chart export button
        const chartExportBtn = document.createElement("button");
        chartExportBtn.type = "button";
        chartExportBtn.className = "admin-btn admin-btn-secondary agency-chart-export-btn";
        chartExportBtn.innerHTML = '<i class="bi bi-image" aria-hidden="true"></i> ' + t("تصدير الرسم البياني", "Export Chart");
        chartExportBtn.addEventListener("click", function () {
          const date = new Date().toISOString().slice(0, 10);
          const link = document.createElement("a");
          link.href = canvas.toDataURL("image/png");
          link.download = (payload.metadata.report_code || "report") + "_chart_" + date + ".png";
          link.click();
        });
        chartSection.appendChild(chartExportBtn);
        root.appendChild(chartSection);
      }
    }

    // Data table
    const rows = payload.breakdowns || [];
    if (rows.length) {
      const tableSection = document.createElement("section");
      tableSection.className = "agency-table-section";
      tableSection.setAttribute("aria-labelledby", "agency-table-title");
      const tableTitle = document.createElement("h2");
      tableTitle.id = "agency-table-title";
      tableTitle.textContent = t("جدول البيانات التجميعية", "Aggregated Data Table");
      tableSection.appendChild(tableTitle);

      const table = document.createElement("table");
      table.className = "agency-table";
      const caption = document.createElement("caption");
      caption.textContent = payload.metadata.report_title_ar;
      table.appendChild(caption);
      const columnLabels = payload.column_labels || {};
      const headers = Object.keys(rows[0]);
      const thead = document.createElement("thead");
      const tr = document.createElement("tr");
      headers.forEach((h) => { const th = document.createElement("th"); th.scope = "col"; th.textContent = columnLabels[h] || h; tr.appendChild(th); });
      thead.appendChild(tr);
      table.appendChild(thead);
      const tbody = document.createElement("tbody");
      rows.forEach((row) => { const r = document.createElement("tr"); headers.forEach((h) => { const td = document.createElement("td"); td.textContent = row[h] == null ? "—" : String(row[h]); r.appendChild(td); }); tbody.appendChild(r); });
      table.appendChild(tbody);
      tableSection.appendChild(table);
      root.appendChild(tableSection);
    } else {
      const empty = document.createElement("div");
      empty.className = "agency-alert";
      empty.textContent = t("لا توجد بيانات مطابقة للفلاتر المحددة. يرجى تعديل المحافظة أو اللواء أو المنطقة أو الفترة الزمنية.", "No matching data for the selected filters. Please adjust the governorate, district, area or time period.");
      root.appendChild(empty);
    }

    // Export controls — CSV only (no JSON, PDF, Excel, Print)
    const exports = document.createElement("div");
    exports.className = "agency-export-actions";
    const base = "/api/admin/agency-reports/" + encodeURIComponent(payload.metadata.agency_code) + "/reports/" + encodeURIComponent(payload.metadata.report_code);
    if (payload.exports && payload.exports.csv) {
      const date = new Date().toISOString().slice(0, 10);
      const a = document.createElement("a");
      a.href = base + "/export.csv" + window.location.search;
      a.className = "admin-btn admin-btn-secondary";
      a.download = (payload.metadata.report_code || "report") + "_" + date + ".csv";
      a.innerHTML = '<i class="bi bi-file-earmark-spreadsheet" aria-hidden="true"></i> ' + t("تصدير CSV", "Export CSV");
      exports.appendChild(a);
    }
    root.appendChild(exports);
  }

  function loadReport() {
    const agencyCode = page.dataset.agencyCode;
    const reportCode = page.dataset.reportCode;
    const form = document.getElementById("agency-report-filters");
    const formData = form ? new FormData(form) : new FormData();
    // Remove empty values
    const params = new URLSearchParams();
    formData.forEach((v, k) => { if (v && v.trim()) params.set(k, v.trim()); });
    const query = params.toString();

    if (root) root.innerHTML = '<div class="agency-loading" role="status"><i class="bi bi-hourglass-split" aria-hidden="true"></i> ' + t("جاري تحميل البيانات...", "Loading data...") + "</div>";

    api("/api/admin/agency-reports/" + encodeURIComponent(agencyCode) + "/reports/" + encodeURIComponent(reportCode) + (query ? "?" + query : ""))
      .then(renderReport)
      .catch(() => {
        if (root) root.innerHTML = '<div class="agency-alert agency-alert--error"><i class="bi bi-exclamation-circle" aria-hidden="true"></i> ' + t("تعذر تحميل التقرير. يرجى المحاولة مرة أخرى أو التواصل مع مسؤول النظام.", "Unable to load the report. Please try again or contact the system administrator.") + "</div>";
      });
  }

  const type = page.dataset.agencyReportsPage;

  if (type === "index") {
    api("/api/admin/agency-reports/catalog")
      .then(renderIndex)
      .catch(() => {
        if (root) root.textContent = t("تعذر تحميل الجهات الرسمية.", "Unable to load agencies.");
      });
  }

  if (type === "agency") {
    api("/api/admin/agency-reports/" + encodeURIComponent(page.dataset.agencyCode) + "/reports")
      .then(renderAgency)
      .catch(() => {
        if (root) root.textContent = t("تعذر تحميل تقارير الجهة.", "Unable to load agency reports.");
      });
  }

  if (type === "report") {
    const filtersForm = document.getElementById("agency-report-filters");
    if (filtersForm) filtersForm.addEventListener("submit", (e) => { e.preventDefault(); loadReport(); });
    loadReport();
  }
})();
